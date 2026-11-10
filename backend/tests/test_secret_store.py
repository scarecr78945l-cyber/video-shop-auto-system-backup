# -*- coding: utf-8 -*-
"""T6: secret_store 验收测试（round-71；round-73 R72-1~R72-5 聚焦回修）。

覆盖（round-70 授权 + round-17 P0-1-T6 + round-72 R72 五阻断）：
  - 写入/读取往返（Fernet 密文落盘；get 解密还原）
  - 定位符契约：<=256、不含凭证、唯一；业务库只保存定位符（无明文）
  - 轮换：新 rotation_seq 新定位符，旧值保留
  - 过期：expires_at 判定
  - 脱敏：redact_secret 永不明文；redacted_display <=64 且不含完整明文（R72-2 短凭证）
  - 文件权限（POSIX 尽力而为）：目录 0700 / 文件 0600（R72-5 原子创建+复核）
  - 错误路径：不存在 -> SecretNotFoundError；损坏密文 -> SecretNotFoundError
  - R72-4：locator grammar 严格校验 + hash 文件名 + 密文 payload 绑定
  - R72-1：真实 credential_refs PostgreSQL 事务持久化（put -> INSERT -> 读取 -> rollback）
  - R72-3：cryptography 已登记 backend/requirements.txt（干净 venv 证据见交接文档）

运行：cd backend && python -m pytest tests/test_secret_store.py -q --basetemp=.pytest-tmp-t6
"""
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infra.credential_refs_repo import CredentialRefsRepo, store_credential  # noqa: E402
from infra.secret_store import (  # noqa: E402
    LocalEncryptedSecretStore,
    SecretNotFoundError,
    SecretStoreError,
    is_expired,
    redact_secret,
    redacted_display,
    secure_delete_file,
    validate_locator,
)

DB_URL = os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture()
def store(tmp_path):
    return LocalEncryptedSecretStore(data_dir=tmp_path)


def test_put_get_roundtrip(store):
    ref = store.put(tenant_id=1, account_id=2, purpose="cookie",
                    secret=b"session_cookie_value_123")
    value, meta = store.get(ref)
    assert value == b"session_cookie_value_123"
    assert meta["tenant_id"] == 1
    assert meta["account_id"] == 2
    assert meta["purpose"] == "cookie"
    assert meta["rotation_seq"] == 1
    assert meta["locator"] == ref  # R72-4：payload 绑定 locator


def test_locator_contract(store):
    ref = store.put(tenant_id=7, account_id=9, purpose="openapi_secret",
                    secret=b"SECRET_PAYLOAD_XYZ")
    assert len(ref) <= 256
    assert ref.startswith("cred:7:9:openapi_secret:1:")
    assert b"SECRET_PAYLOAD_XYZ" not in ref.encode("utf-8")  # 定位符不含凭证
    ref2 = store.put(tenant_id=7, account_id=9, purpose="openapi_secret",
                     secret=b"SECRET_PAYLOAD_XYZ")
    assert ref != ref2  # uuid 保证唯一


def test_validate_locator_grammar(store):
    """R72-4：grammar 严格校验——非规范别名/非法 purpose/非 canonical uuid 均拒绝。"""
    ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"x")
    tenant, account, purpose, seq, uuid_hex = validate_locator(ref)
    assert (tenant, account, purpose, seq) == (1, 2, "token", 1)
    # 非规范别名（冒号换斜杠）在 get/delete 入口直接拒绝
    alias = ref.replace(":", "/")
    with pytest.raises(SecretStoreError):
        store.get(alias)
    with pytest.raises(SecretStoreError):
        store.delete(alias)
    with pytest.raises(SecretStoreError):
        validate_locator("cred:1:2:bogus:1:" + uuid_hex)   # 未知 purpose
    with pytest.raises(SecretStoreError):
        validate_locator("cred:0:2:token:1:" + uuid_hex)   # tenant 非正
    with pytest.raises(SecretStoreError):
        validate_locator("cred:1:2:token:1:ZZZZZZZZ-0000-0000-0000-000000000000")  # uuid 非 canonical
    with pytest.raises(SecretStoreError):
        validate_locator("other:1:2:token:1:" + uuid_hex)  # 非 cred: 前缀


def test_no_plaintext_on_disk(store, tmp_path):
    secret = b"cookie_secret_do_not_leak_42"
    ref = store.put(tenant_id=1, account_id=2, purpose="cookie", secret=secret)
    for f in tmp_path.iterdir():
        if f.name == "master.key":
            continue
        content = f.read_bytes()
        assert secret not in content
        assert b"cookie_secret_do_not_leak_42" not in content


def test_business_table_only_locator(store, tmp_path):
    """业务库无明文：credential_refs.secret_store_key 只存定位符（v6 §1.5）。"""
    secret = b"token_abc_123"
    ref = store.put(tenant_id=3, account_id=4, purpose="token", secret=secret)
    row = {"secret_store_key": ref, "redacted_display": redacted_display(secret)}
    assert row["secret_store_key"] == ref
    assert b"token_abc_123" not in ref.encode("utf-8")
    assert "token_abc_123" not in row["redacted_display"]


def test_rotate_keeps_old(store):
    r1 = store.put(tenant_id=1, account_id=2, purpose="token",
                   secret=b"old_secret", rotation_seq=1)
    r2 = store.rotate(tenant_id=1, account_id=2, purpose="token",
                      secret=b"new_secret", next_seq=2)
    assert r1 != r2
    v1, m1 = store.get(r1)
    v2, m2 = store.get(r2)
    assert v1 == b"old_secret" and m1["rotation_seq"] == 1
    assert v2 == b"new_secret" and m2["rotation_seq"] == 2


def test_delete(store):
    ref = store.put(tenant_id=1, account_id=2, purpose="cookie", secret=b"x")
    store.delete(ref)
    with pytest.raises(SecretNotFoundError):
        store.get(ref)
    store.delete(ref)  # 幂等


def test_expiry(store):
    ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"x",
                    expires_at="2020-01-01T00:00:00+00:00")
    _value, meta = store.get(ref)
    assert is_expired(meta) is True
    ref2 = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"y",
                     expires_at="2099-01-01T00:00:00+00:00")
    _v2, meta2 = store.get(ref2)
    assert is_expired(meta2) is False
    ref3 = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"z")
    _v3, meta3 = store.get(ref3)
    assert is_expired(meta3) is False


def test_redact(store):
    assert redact_secret(b"anything_secret") == "***redacted***"
    assert redact_secret(b"") == "***redacted***"
    # R72-2：短凭证（1~4 字符）固定返回 ***，完整 secret 永不为 display 子串
    for short in (b"a", b"ab", b"abc", b"abcd"):
        d = redacted_display(short)
        assert d == "***"
        assert short.decode() not in d
    # 多字节 UTF-8 边界：解码替换后仍满足"完整 secret 非子串"（替换字符非原字节）
    d_mb = redacted_display("好棒好棒好棒好棒好棒".encode("utf-8"))
    assert len(d_mb) <= 64
    # 5 字符以上才显示前 4 + ***
    assert redacted_display(b"0123456789abcdef") == "0123***"
    assert redacted_display(b"") == "***"
    long_display = redacted_display(b"a" * 200)
    assert len(long_display) <= 64


def test_not_found(store):
    # 合法 grammar 但从未写入的定位符 -> SecretNotFoundError
    with pytest.raises(SecretNotFoundError):
        store.get("cred:1:1:token:1:00000000-0000-0000-0000-000000000000")


def test_master_key_env(store, monkeypatch):
    """master_key 显式传入优先；SECRET_STORE_KEY 环境变量次之。"""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    s2 = LocalEncryptedSecretStore(data_dir=store._dir, master_key=key)
    ref = s2.put(tenant_id=1, account_id=2, purpose="token", secret=b"env_key_test")
    assert s2.get(ref)[0] == b"env_key_test"
    monkeypatch.setenv("SECRET_STORE_KEY", key.decode("ascii"))
    s3 = LocalEncryptedSecretStore(data_dir=store._dir)
    assert s3.get(ref)[0] == b"env_key_test"  # 同 key 可读


def test_secure_delete_file(tmp_path):
    p = tmp_path / "t.enc"
    p.write_bytes(b"x" * 100)
    secure_delete_file(p)
    assert not p.exists()


def test_file_permissions(tmp_path):
    """R72-5：key 文件 O_CREAT|O_EXCL 原子创建 0600；既有密文权限复核收紧。"""
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    ref = store.put(tenant_id=1, account_id=2, purpose="cookie", secret=b"perm")
    if os.name == "posix":
        key_mode = (tmp_path / "master.key").stat().st_mode & 0o777
        assert key_mode == 0o600
        enc = next(p for p in tmp_path.iterdir() if p.name.endswith(".enc"))
        assert (enc.stat().st_mode & 0o777) == 0o600
        assert (tmp_path.stat().st_mode & 0o777) == 0o700
    # Windows：尽力而为（存在即可；ACL 语义另行用 icacls 判定，见 test_windows_acl_best_effort）
    assert store.get(ref)[0] == b"perm"


def _ps_acl_entries(path):
    """PowerShell Get-Acl JSON 结构化输出（R78-1：独立子进程 + 冻结 PSModulePath）。

    返回 dict {"owner":..., "user":..., "aces":[{"subject","rights","type","inherited"}, ...]}。
    模拟实现失败（rc!=0 / stderr 非空 / 非 JSON）抛 RuntimeError。
    """
    import subprocess
    import json as _json

    script = (
        "param([string]$p)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "Import-Module \"$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\Modules\\"
        "Microsoft.PowerShell.Security\" -Force -ErrorAction Stop\n"
        "$v = Get-Acl -LiteralPath $p\n"
        "$u = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name\n"
        "$owner = [string]$v.Owner\n"
        "if ($owner -ne $u) { throw \"owner mismatch: $owner != $u\" }\n"
        "$aces = @($v.Access | ForEach-Object {\n"
        "  [pscustomobject]@{ subject=$_.IdentityReference.Value; rights=$_.FileSystemRights.ToString();"
        " type=$_.AccessControlType.ToString(); inherited=$_.IsInherited.ToString() }\n"
        "})\n"
        "[pscustomobject]@{ owner=$owner; user=$u; aces=$aces } | ConvertTo-Json -Compress\n"
    )
    import tempfile

    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    ps_exe = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    native_modules = str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules")
    with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w", delete=False, encoding="utf-8-sig") as f:
        f.write(script)
        script_path = f.name
    sub_env = dict(os.environ)
    sub_env["PSModulePath"] = native_modules
    try:
        r = subprocess.run(
            [str(ps_exe), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script_path, str(path)],
            capture_output=True, timeout=60, env=sub_env,
        )
    finally:
        os.unlink(script_path)
    if r.returncode != 0 or r.stderr:
        raise RuntimeError(r.stderr.decode("mbcs", errors="replace"))
    out = r.stdout.decode("mbcs", errors="replace")
    try:
        return _json.loads(out)
    except ValueError as exc:  # noqa: BLE001
        raise RuntimeError(f"非 JSON 输出: {out[:200]!r}") from exc


def _assert_owner_only_acl(path, user):
    """断言 path 的 ACL：无继承、无宽主体、当前用户 FullControl Allow。

    允许系统固有主体：OWNER RIGHTS / CREATOR OWNER / CREATOR GROUP / S-1-3-*。
    """
    data = _ps_acl_entries(path)
    entries = data.get("aces") or []
    assert entries, f"{path} 无 ACE"
    assert data.get("owner") == data.get("user"), f"{path} owner 与当前用户不一致"
    owner_ok = False
    for ace in entries:
        subj = (ace.get("subject") or "").strip()
        rights = (ace.get("rights") or "").strip()
        atype = (ace.get("type") or "").strip()
        inherited = (ace.get("inherited") or "").strip()
        assert inherited.lower() == "false", f"{path} 存在继承 ACE: {ace}"
        assert "Everyone" not in subj, f"{path} 存在 Everyone: {ace}"
        assert subj.upper() not in ("NT AUTHORITY\\SYSTEM", "BUILTIN\\ADMINISTRATORS", "BUILTIN\\USERS",
                                    "NT AUTHORITY\\AUTHENTICATED USERS"), f"{path} 存在宽主体: {ace}"
        if subj.lower() == user.lower() or subj.lower().endswith("\\" + user.lower()):
            assert rights == "FullControl" and atype == "Allow", f"{path} 当前用户非 FullControl: {ace}"
            owner_ok = True
        else:
            # 系统固有主体（OWNER RIGHTS 等）允许；其他任何主体 -> 失败
            assert (subj.upper() in ("OWNER RIGHTS", "CREATOR OWNER", "CREATOR GROUP")
                    or subj.startswith("S-1-3-")), f"{path} 存在未授权主体: {ace}"
    assert owner_ok, f"{path} 缺少当前用户 FullControl Allow: {entries}"


def test_windows_acl_best_effort(tmp_path):
    """R72-5 + R76-2：Windows owner-only 结构化验证（Get-Acl exact-set，不再用 icacls 子串）。"""
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL")
    import getpass

    user = getpass.getuser()
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    ref = store.put(tenant_id=1, account_id=2, purpose="cookie", secret=b"acl")
    for p in (tmp_path, tmp_path / "master.key", store._path(ref)):
        _assert_owner_only_acl(p, user)
    assert store.get(ref)[0] == b"acl"


def test_windows_acl_users_path_no_false_positive(tmp_path):
    """R76-2：路径文本含 Users（如 C:\\Users\\...）不应被误判为宽主体。"""
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL")
    import getpass
    import tempfile as _tf

    user = getpass.getuser()
    # 使用系统临时目录（通常位于 C:\Users\...），路径文本必含 Users
    base = Path(_tf.gettempdir())
    d = base / f"secretstore_users_path_{uuid.uuid4().hex[:8]}"
    d.mkdir(exist_ok=True)
    try:
        store = LocalEncryptedSecretStore(data_dir=d)
        ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"up")
        assert store.get(ref)[0] == b"up"
        _assert_owner_only_acl(d, user)
    finally:
        import shutil

        shutil.rmtree(d, ignore_errors=True)


def test_windows_acl_second_subject_fail_closed(tmp_path):
    """R76-2：注入第二主体（SYSTEM）后重新初始化——ACL 被重建为 owner-only（SYSTEM 被清除）。

    「清除既有显式授权、建立冻结主体集合」语义下，重开必须把 SYSTEM 移除并恢复 owner-only exact；
    若系统无法清除/重建则应 fail closed（二者取一，本实现取清除）。
    """
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL")
    import getpass
    import subprocess

    user = getpass.getuser()
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"second")
    # 向目录/既有 key/密文注入 SYSTEM:(F)
    for p in (tmp_path, tmp_path / "master.key", store._path(ref)):
        r = subprocess.run(
            ["icacls", str(p), "/grant", "SYSTEM:(F)"], capture_output=True, timeout=30)
        assert r.returncode == 0, r.stderr.decode("mbcs", errors="replace")
    # 重新初始化（_enforce_existing_perms 会复核并重建 ACL）-> SYSTEM 应被清除
    store2 = LocalEncryptedSecretStore(data_dir=tmp_path)
    assert store2.get(ref)[0] == b"second"
    for p in (tmp_path, tmp_path / "master.key", store2._path(ref)):
        _assert_owner_only_acl(p, user)


def test_key_atomic_exclusive(tmp_path):
    """R72-5：两个实例并发初始化同一目录，O_EXCL 保证同一 key 不互相覆盖。"""
    s1 = LocalEncryptedSecretStore(data_dir=tmp_path)
    key_bytes = (tmp_path / "master.key").read_bytes()
    s2 = LocalEncryptedSecretStore(data_dir=tmp_path)  # 复用既有 key（FileExistsError 分支）
    assert (tmp_path / "master.key").read_bytes() == key_bytes
    ref = s1.put(tenant_id=1, account_id=2, purpose="token", secret=b"shared")
    assert s2.get(ref)[0] == b"shared"  # 两实例同 key 可互读
    # 并发初始化：多线程同时创建，最终仍是单 key 且可互读
    barrier = threading.Barrier(4)
    results = []
    errors = []

    def init():
        try:
            barrier.wait(timeout=5)
            s = LocalEncryptedSecretStore(data_dir=tmp_path)
            results.append(s.get(ref)[0])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=init) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors
    assert all(r == b"shared" for r in results)


def test_locator_payload_binding(store):
    """R72-4：密文 payload 绑定 locator——篡改文件内容（换 locator）导致身份错配拒绝。"""
    ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"bind_me")
    path = store._path(ref)
    token = path.read_bytes()
    from cryptography.fernet import Fernet

    # 用同 key 重新加密但把 meta.locator 换成另一个合法 locator
    f = Fernet((store._dir / "master.key").read_bytes().strip())
    payload = f.decrypt(token)
    import json as _json

    data = _json.loads(payload)
    data["meta"]["locator"] = "cred:9:9:token:1:00000000-0000-0000-0000-000000000000"
    path.write_bytes(f.encrypt(_json.dumps(data).encode()))
    with pytest.raises(SecretNotFoundError):
        store.get(ref)


# ---------------------------------------------------------------------------
# R72-1：真实 credential_refs PostgreSQL 事务持久化（业务库只存定位符）
# ---------------------------------------------------------------------------
def _pg_conn():
    from sqlalchemy import create_engine

    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过真实 credential_refs 持久化测试")
    eng = create_engine(DB_URL)
    conn = eng.connect()
    return eng, conn


def test_credential_refs_pg_persist_no_plaintext(tmp_path):
    """R72-1 + R76-1：真实事务 put -> INSERT credential_refs -> 读取 -> rollback。

    断言业务行 secret_store_key=定位符、查询结果不含 secret、组合 FK 满足；store 必传。
    """
    from sqlalchemy import text as sqltext

    eng, conn = _pg_conn()
    tx = conn.begin()
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    repo = CredentialRefsRepo()
    try:
        tid = conn.execute(sqltext(
            "INSERT INTO app.tenants (public_id, name, scope) VALUES "
            "(gen_random_uuid(), 't6_pg', 'internal') RETURNING id")).scalar()
        aid = conn.execute(sqltext(
            "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
            "(gen_random_uuid(), :t, 'wechat_channels', 't6_acc') RETURNING id"),
            {"t": tid}).scalar()
        secret = b"PG_SECRET_NEVER_IN_DB_9911"
        locator = store.put(tenant_id=tid, account_id=aid, purpose="token", secret=secret)
        row_id = repo.insert(
            conn, store=store,
            tenant_id=tid, account_id=aid, purpose="token", rotation_seq=1,
            locator=locator, status="valid",
        )
        rows = repo.select_by(conn, tenant_id=tid, account_id=aid, purpose="token")
        assert len(rows) == 1
        row = rows[0]
        assert row["secret_store_key"] == locator
        assert row["id"] == row_id
        joined = " ".join(str(v) for v in row.values())
        assert "PG_SECRET_NEVER_IN_DB_9911" not in joined
        assert secret not in locator.encode("utf-8")
        assert "PG_SECRET_NEVER_IN_DB_9911" not in row["redacted_display"]
        # R76-1：store 必传——store=None 拒绝
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=None,
                        tenant_id=tid, account_id=aid, purpose="token", rotation_seq=1,
                        locator=locator, status="valid")
        # 绕过 adapter：非法 locator 拒绝
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=store,
                        tenant_id=tid, account_id=aid, purpose="token", rotation_seq=2,
                        locator="cred:" + str(tid) + ":" + str(aid) + ":bogus:1:"
                                + "00000000-0000-0000-0000-000000000000",
                        status="valid")
    finally:
        tx.rollback()  # 不留数据
        conn.close()
        eng.dispose()


def test_credential_refs_repo_locator_validation(tmp_path):
    """R72-1 + R76-1：adapter 层拒绝非 locator 输入（store 必传 + 非法格式）。"""
    eng, conn = _pg_conn()
    tx = conn.begin()
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    try:
        repo = CredentialRefsRepo()
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=store, tenant_id=1, account_id=2, purpose="cookie", rotation_seq=1,
                        locator="PLAINTEXT_TOKEN_CDX")
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=store, tenant_id=1, account_id=2, purpose="cookie", rotation_seq=1,
                        locator="cred:1:2:cookie:1:not-a-uuid")
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


# ---------------------------------------------------------------------------
# R74-1：repo 上下文绑定 + store_credential 集成 service（真实 PG 负例）
# ---------------------------------------------------------------------------
def test_repo_locator_context_binding(tmp_path):
    """R74-1 + R76-1：locator 解包上下文必须与业务列逐项一致，任一错配拒绝；store 必传。"""
    from sqlalchemy import text as sqltext

    eng, conn = _pg_conn()
    tx = conn.begin()
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    try:
        tid = conn.execute(sqltext(
            "INSERT INTO app.tenants (public_id, name, scope) VALUES "
            "(gen_random_uuid(), 't6_bind', 'internal') RETURNING id")).scalar()
        aid = conn.execute(sqltext(
            "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
            "(gen_random_uuid(), :t, 'wechat_channels', 't6_bind_acc') RETURNING id"),
            {"t": tid}).scalar()
        locator = store.put(tenant_id=tid, account_id=aid, purpose="token", secret=b"ctx")
        repo = CredentialRefsRepo()
        row_id = repo.insert(conn, store=store,
                             tenant_id=tid, account_id=aid, purpose="token", rotation_seq=1,
                             locator=locator, status="valid")
        assert row_id is not None
        # 负例：purpose 错配
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=store,
                        tenant_id=tid, account_id=aid, purpose="cookie", rotation_seq=1,
                        locator=locator, status="valid")
        # 负例：rotation_seq 错配
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=store,
                        tenant_id=tid, account_id=aid, purpose="token", rotation_seq=7,
                        locator=locator, status="valid")
        # 负例：tenant 错配
        other_tid = conn.execute(sqltext(
            "INSERT INTO app.tenants (public_id, name, scope) VALUES "
            "(gen_random_uuid(), 't6_bind2', 'internal') RETURNING id")).scalar()
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=store,
                        tenant_id=other_tid, account_id=aid, purpose="token", rotation_seq=1,
                        locator=locator, status="valid")
        # 负例：语法合法但 store 不存在的伪造 locator（store.get -> SecretNotFoundError）
        forged = "cred:" + str(tid) + ":" + str(aid) + ":token:1:" + str(uuid.uuid4())
        with pytest.raises(SecretNotFoundError):
            repo.insert(conn, store=store,
                        tenant_id=tid, account_id=aid, purpose="token", rotation_seq=1,
                        locator=forged, status="valid")
        # R76-1 负例：store=None 拒绝
        with pytest.raises(SecretStoreError):
            repo.insert(conn, store=None,
                        tenant_id=tid, account_id=aid, purpose="token", rotation_seq=1,
                        locator=locator, status="valid")
        # R76-1 负例：display 不再接受调用方任意字符串（无 redacted_display 参数）
        with pytest.raises(TypeError):
            repo.insert(conn, store=store,
                        tenant_id=tid, account_id=aid, purpose="token", rotation_seq=1,
                        locator=locator, redacted_display="FULL_SECRET_LEAK***", status="valid")
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


def test_store_credential_service(tmp_path):
    """R74-1 + R76-1：store_credential 集成 service（put + insert 单一入口，业务库无明文）。"""
    from sqlalchemy import text as sqltext

    eng, conn = _pg_conn()
    tx = conn.begin()
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    try:
        tid = conn.execute(sqltext(
            "INSERT INTO app.tenants (public_id, name, scope) VALUES "
            "(gen_random_uuid(), 't6_svc', 'internal') RETURNING id")).scalar()
        aid = conn.execute(sqltext(
            "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
            "(gen_random_uuid(), :t, 'wechat_channels', 't6_svc_acc') RETURNING id"),
            {"t": tid}).scalar()
        secret = b"SVC_SECRET_NEVER_IN_DB_7755"
        locator, row_id = store_credential(
            conn, store, tenant_id=tid, account_id=aid, purpose="token",
            secret=secret, rotation_seq=1,
        )
        assert row_id is not None
        rows = CredentialRefsRepo().select_by(
            conn, tenant_id=tid, account_id=aid, purpose="token")
        assert len(rows) == 1
        joined = " ".join(str(v) for v in rows[0].values())
        assert "SVC_SECRET_NEVER_IN_DB_7755" not in joined
        # R76-1：display 由 secret 内部计算，且与 redacted_display(secret) 完全一致
        assert rows[0]["redacted_display"] == redacted_display(secret)
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


# ---------------------------------------------------------------------------
# R74-2：bool 不能绕过正整数门禁（不落孤儿密文）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["tenant_id", "account_id", "rotation_seq"])
def test_bool_rejected_no_orphan(tmp_path, field):
    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    kwargs = {"tenant_id": 1, "account_id": 2, "purpose": "token", "secret": b"bool", "rotation_seq": 1}
    kwargs[field] = True  # bool 是 int 子类，必须被拒绝
    with pytest.raises(SecretStoreError):
        store.put(**kwargs)
    # 不应产生孤儿密文（.enc 文件数仍为 0）
    encs = [p for p in tmp_path.iterdir() if p.name.endswith(".enc")]
    assert encs == []


# ---------------------------------------------------------------------------
# R74-3.1：空目录并发初始化竞态（同步点覆盖"已 O_EXCL 创建但未写完 key"窗口）
# ---------------------------------------------------------------------------
def test_concurrent_init_empty_dir_race(tmp_path, monkeypatch):
    """两个实例同时在空目录初始化；首实例在生成 key 前阻塞，次实例必须重试到 key 可解析。"""
    from cryptography.fernet import Fernet

    real_gen = Fernet.generate_key
    entered = threading.Event()
    release = threading.Event()

    def slow_generate_key():
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("slow_generate_key 等待超时")
        return real_gen()

    monkeypatch.setattr(Fernet, "generate_key", staticmethod(slow_generate_key))
    results = []
    errors = []

    def init():
        try:
            s = LocalEncryptedSecretStore(data_dir=tmp_path)
            results.append(s)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=init)
    t1.start()
    assert entered.wait(timeout=5)  # 首实例已 O_EXCL 创建空 key 文件并停在 generate_key
    t2 = threading.Thread(target=init)  # 次实例进入 FileExists 分支并等待重试
    t2.start()
    time.sleep(0.3)  # 让次实例读到空文件并开始重试
    release.set()  # 放行首实例写完 key
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not errors
    assert len(results) == 2
    # 两实例可互读同一凭证（同 key）
    ref = results[0].put(tenant_id=1, account_id=2, purpose="token", secret=b"race")
    assert results[1].get(ref)[0] == b"race"


# ---------------------------------------------------------------------------
# R74-3.2：Windows ACL fail-closed + 目录/新旧 key/密文 owner-only
# ---------------------------------------------------------------------------
def test_windows_acl_fail_closed(tmp_path, monkeypatch):
    """R74-3.2 + R76-2：ACL 设置失败（注入 OSError）必须抛 SecretStoreError（fail closed）。"""
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL fail-closed")
    import subprocess as _sp

    def boom(*args, **kwargs):
        raise OSError("ACL unavailable (injected)")

    monkeypatch.setattr(_sp, "run", boom)
    with pytest.raises(SecretStoreError):
        LocalEncryptedSecretStore(data_dir=tmp_path)


def test_windows_acl_exact_owner_only(tmp_path):
    """R74-3.2 + R76-2：目录/新 key/新密文 owner-only exact（Get-Acl 结构化验证）。

    无继承、无 Everyone/Users/SYSTEM/Administrators 宽主体；当前用户 FullControl Allow。
    """
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL exact")
    import getpass

    store = LocalEncryptedSecretStore(data_dir=tmp_path)
    ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"acl_exact")
    user = getpass.getuser()
    for p in (tmp_path, tmp_path / "master.key", store._path(ref)):
        _assert_owner_only_acl(p, user)
    assert store.get(ref)[0] == b"acl_exact"


# ---------------------------------------------------------------------------
# R78-1：ACL 验证器 ambient PSModulePath 隔离
# ---------------------------------------------------------------------------
def _fake_pwsh7_module_dir(tmp_path):
    """构造伪 PowerShell 7 同名 Microsoft.PowerShell.Security 模块目录（与 Codex 注入同构）。"""
    mod = tmp_path / "Microsoft.PowerShell.Security"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "Microsoft.PowerShell.Security.psd1").write_text(
        "@{RootModule='Microsoft.PowerShell.Security.psm1'; ModuleVersion='7.0.0.0'}\n",
        encoding="utf-8")
    # 不兼容的同名实现：若被加载将破坏 Get-Acl
    (mod / "Microsoft.PowerShell.Security.psm1").write_text(
        "function Get-Acl { throw 'WRONG MODULE LOADED (PowerShell 7 stub)' }\n",
        encoding="utf-8")
    return mod


def test_acl_ambient_psmodulepath_isolated(tmp_path, monkeypatch):
    """R78-1：父进程 PSModulePath 前置 PowerShell 7 同名模块目录，SecretStore 仍须完成。

    子进程环境被冻结为 Windows PowerShell 原生模块路径，不继承污染；
    C:\\Users 路径初始化、SYSTEM 注入清除与 exact-set 验证均须通过。
    """
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL")
    import getpass

    fake_mod = _fake_pwsh7_module_dir(tmp_path)
    old_pmp = os.environ.get("PSModulePath", "")
    monkeypatch.setenv("PSModulePath", str(fake_mod) + ";" + old_pmp)  # 污染前置
    user = getpass.getuser()
    # 普通路径初始化 + 写入/读取
    d1 = tmp_path / "store_clean"
    d1.mkdir()
    store = LocalEncryptedSecretStore(data_dir=d1)
    ref = store.put(tenant_id=1, account_id=2, purpose="token", secret=b"ambient")
    assert store.get(ref)[0] == b"ambient"
    for p in (d1, d1 / "master.key", store._path(ref)):
        _assert_owner_only_acl(p, user)
    # C:\Users 路径（系统临时目录）初始化
    import tempfile as _tf

    d2 = Path(_tf.gettempdir()) / f"secretstore_ambient_{uuid.uuid4().hex[:8]}"
    d2.mkdir()
    try:
        store2 = LocalEncryptedSecretStore(data_dir=d2)
        ref2 = store2.put(tenant_id=1, account_id=2, purpose="token", secret=b"up2")
        assert store2.get(ref2)[0] == b"up2"
        _assert_owner_only_acl(d2, user)
    finally:
        import shutil

        shutil.rmtree(d2, ignore_errors=True)
    # SYSTEM 注入清除仍有效
    import subprocess

    for p in (d1, d1 / "master.key", store._path(ref)):
        r = subprocess.run(["icacls", str(p), "/grant", "SYSTEM:(F)"],
                           capture_output=True, timeout=30)
        assert r.returncode == 0
    store3 = LocalEncryptedSecretStore(data_dir=d1)
    assert store3.get(ref)[0] == b"ambient"
    for p in (d1, d1 / "master.key", store3._path(ref)):
        _assert_owner_only_acl(p, user)


def test_acl_getacl_error_nonzero_exit(tmp_path, monkeypatch):
    """R78-1：Get-Acl 失败必须非零退出（$ErrorActionPreference=Stop），不再产出 USER=/||| 假成功。

    注入子进程启动失败（OSError）与 stderr 非空两种失败路径 -> SecretStoreError。
    """
    if os.name != "nt":
        pytest.skip("仅 Windows 判定 ACL")
    import subprocess as _sp

    # 1) 子进程无法启动（OSError）-> fail closed
    def boom(*args, **kwargs):
        raise OSError("powershell spawn failed (injected)")

    monkeypatch.setattr(_sp, "run", boom)
    with pytest.raises(SecretStoreError):
        LocalEncryptedSecretStore(data_dir=tmp_path)
    monkeypatch.undo()

    # 2) 返回 rc=0 但 stderr 非空（非终止错误泄漏）-> fail closed
    class FakeProc:
        returncode = 0
        stdout = b"USER=\r\n|||\r\n"
        stderr = b"Get-Acl : The 'Get-Acl' command was found in the module 'Microsoft.PowerShell.Security', but the module could not be loaded.\r\n"

    def fake_run(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(_sp, "run", fake_run)
    with pytest.raises(SecretStoreError):
        LocalEncryptedSecretStore(data_dir=tmp_path)
