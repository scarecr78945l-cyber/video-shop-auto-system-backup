# -*- coding: utf-8 -*-
"""secret_store（P0-1 T6，round-71 初版；round-73 R72-1~R72-5 聚焦回修）。

契约：
- 15-数据字典.md v6 §1.5 `credential_refs`：`secret_store_key varchar(256)` 为 **secret store 定位符**，
  凭证本体只进 secret store；业务库（app.credential_refs）不得存明文。
- round-17 P0-1-T6：`backend/infra/secret_store.py`（接口 + 本地实现）+ 脱敏测试。
- 红线：凭证不得进入日志、API 响应或 migration seed。

round-73 回修（Codex round-72 R72-1~R72-5）：
- R72-2：短凭证脱敏——`redacted_display` 长度 <=4 固定返回 `***`，完整 secret 永不为 display 子串；
- R72-3：`cryptography` 登记依赖（backend/requirements.txt）并提供干净 venv 重建证据；
- R72-4：locator 严格 grammar 校验（cred:<tenant>:<account>:<purpose>:<seq>:<uuid>，purpose 枚举、
  正整数、canonical UUID），文件名改用 locator 稳定 hash（sha256），密文 payload 绑定原始 locator，
  解密后复核——非规范别名不再可读写同一凭证；
- R72-5：主密钥 O_CREAT|O_EXCL 原子创建（0600）+ 启动权限复核（过宽收紧/fail closed）；
  密文原子临时文件 + os.replace（0600）；Windows owner-only ACL 尽力实现（icacls /inheritance:r）
  并在测试中用 icacls 输出做可判定断言；并发初始化门禁（O_EXCL 保证双进程不同 key 不互相覆盖）；
- R72-1：真实 credential_refs 持久化 adapter（见 backend/infra/credential_refs_repo.py）
  与 PostgreSQL 事务测试（put -> INSERT -> 读取 -> rollback，断言业务行不含明文）。

实现：
- `SecretStore`：抽象接口（put/get/delete/rotate）。
- `LocalEncryptedSecretStore`：本地受限目录 + Fernet（cryptography）对称加密文件存储。
- `validate_locator()`：locator grammar 校验（put/get/delete/rotate 全入口）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

SECRET_STORE_KEY_ENV = "SECRET_STORE_KEY"
MASTER_KEY_FILE = "master.key"
MAX_LOCATOR_LEN = 256
DISPLAY_MAX_LEN = 64
DIR_MODE = 0o700
KEY_MODE = 0o600
FILE_MODE = 0o600

# R72-4：locator 严格 grammar（cred:<tenant_id>:<account_id>:<purpose>:<rotation_seq>:<uuid>）
LOCATOR_RE = re.compile(
    r"^cred:(?P<tenant>\d+):(?P<account>\d+):(?P<purpose>[a-z_]+):(?P<seq>\d+):"
    r"(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
# v6 §1.5 enum_credential_purpose
CREDENTIAL_PURPOSES = {"cookie", "token", "openapi_secret", "proxy_credential"}


class SecretStoreError(Exception):
    """secret_store 契约错误。"""


class SecretNotFoundError(SecretStoreError):
    """定位符不存在或密文无法解密。"""


class SecretStore(ABC):
    """secret_store 抽象接口（T6）。"""

    @abstractmethod
    def put(
        self,
        tenant_id: int,
        account_id: int,
        purpose: str,
        secret: bytes,
        rotation_seq: int = 1,
        expires_at: Optional[str] = None,
    ) -> str:
        """写入凭证，返回定位符（secret_store_key 值，不含凭证）。"""

    @abstractmethod
    def get(self, locator: str) -> Tuple[bytes, dict[str, Any]]:
        """按定位符读取；返回 (secret, meta)。不存在/无法解密抛 SecretNotFoundError。"""

    @abstractmethod
    def delete(self, locator: str) -> None:
        """删除定位符对应凭证（幂等）。"""

    @abstractmethod
    def rotate(
        self,
        tenant_id: int,
        account_id: int,
        purpose: str,
        secret: bytes,
        next_seq: int,
        expires_at: Optional[str] = None,
    ) -> str:
        """轮换：以新 rotation_seq 写入，返回新定位符（旧值保留）。"""


def redact_secret(_secret: bytes) -> str:
    """日志/API 响应统一脱敏：凭证值永不以明文形式出现。"""
    return "***redacted***"


def redacted_display(secret: bytes) -> str:
    """credential_refs.redacted_display（varchar(64)）兼容显示串（R72-2）。

    规则：长度 >4 时取前 4 个可打印字符 + '***'；长度 <=4（含空）固定返回 '***'，
    保证完整 secret 永不为 display 子串；总长 <= 64。
    """
    text = secret.decode("utf-8", errors="replace").strip()
    if len(text) <= 4:
        return "***"
    head = text[:4]
    return (head + "***")[:DISPLAY_MAX_LEN]


def validate_locator(locator: str) -> Tuple[int, int, str, int, str]:
    """R72-4：locator grammar 严格校验；非法抛 SecretStoreError。

    返回 (tenant_id, account_id, purpose, rotation_seq, uuid_hex)。
    拒绝：非 cred: 前缀、非正整数、未知 purpose、非 canonical UUID、超长。
    """
    if not isinstance(locator, str) or len(locator) > MAX_LOCATOR_LEN:
        raise SecretStoreError(f"locator 非法（长度/类型）: {locator!r}")
    m = LOCATOR_RE.match(locator)
    if not m:
        raise SecretStoreError(f"locator grammar 不匹配: {locator!r}")
    purpose = m.group("purpose")
    if purpose not in CREDENTIAL_PURPOSES:
        raise SecretStoreError(f"locator purpose 非冻结枚举: {purpose!r}")
    tenant_id = int(m.group("tenant"))
    account_id = int(m.group("account"))
    seq = int(m.group("seq"))
    if tenant_id <= 0 or account_id <= 0 or seq <= 0:
        raise SecretStoreError(f"locator tenant/account/seq 必须为正整数: {locator!r}")
    uuid_hex = m.group("uuid")
    try:
        u = uuid.UUID(uuid_hex)
    except ValueError as exc:  # noqa: BLE001
        raise SecretStoreError(f"locator uuid 非 canonical: {uuid_hex!r}") from exc
    if str(u) != uuid_hex:
        raise SecretStoreError(f"locator uuid 非 canonical（需小写规范形）: {uuid_hex!r}")
    return (tenant_id, account_id, purpose, seq, uuid_hex)


class LocalEncryptedSecretStore(SecretStore):
    """本地受限目录 + Fernet 对称加密文件存储（T6，round-73 加固）。"""

    def __init__(self, data_dir: Path, master_key: Optional[bytes] = None):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._enforce_dir_perm()
        self._enforce_existing_perms()  # R72-5：启动复核既有 key/密文权限
        if master_key is not None:
            try:
                self._fernet = Fernet(master_key)
            except (ValueError, TypeError) as exc:  # noqa: BLE001
                raise SecretStoreError(f"master_key 非法（{exc}）") from exc
            return
        env_key = os.environ.get(SECRET_STORE_KEY_ENV, "").strip()
        if env_key:
            try:
                self._fernet = Fernet(env_key.encode("ascii"))
            except (ValueError, TypeError) as exc:  # noqa: BLE001
                raise SecretStoreError(f"SECRET_STORE_KEY 非法（{exc}）") from exc
            return
        self._fernet = self._load_or_create_key()

    # ------------------------------------------------------------------ 权限
    def _enforce_dir_perm(self) -> None:
        self._chmod(self._dir, DIR_MODE)
        self._windows_owner_only(self._dir)  # R74-3.2：目录也执行 owner-only ACL

    def _enforce_existing_perms(self) -> None:
        """R72-5 + R74-3.2：启动复核既有 key/密文权限；过宽时收紧（POSIX chmod + Windows ACL）。"""
        key_file = self._dir / MASTER_KEY_FILE
        if key_file.exists():
            self._chmod(key_file, KEY_MODE)
            self._windows_owner_only(key_file)
        for p in self._dir.iterdir():
            if p.is_file() and p.name != MASTER_KEY_FILE and p.name.endswith(".enc"):
                self._chmod(p, FILE_MODE)
                self._windows_owner_only(p)

    def _chmod(self, path: Path, mode: int) -> None:
        try:
            os.chmod(path, mode)
        except (OSError, NotImplementedError):  # noqa: BLE001
            pass  # Windows 无 POSIX mode；由 _windows_owner_only 兜底

    def _windows_owner_only(self, path: Path) -> None:
        """R72-5 + R74-3.2 + R76-2 + R78-1：Windows owner-only DACL，fail closed。

        设置（icacls，无需 SeSecurityPrivilege）：
          - /inheritance:r 移除继承；
          - /remove:g 按 SID 移除 SYSTEM/Administrators/Users/Everyone/Authenticated Users 等宽主体；
          - /grant:r 当前用户 FullControl（目录加 (OI)(CI)）。
        验证（独立子进程 + 冻结环境 + JSON 结构化输出，R78-1）：
          - 使用 Windows PowerShell 5.1 绝对路径，并为子进程构造独立环境：
            PSModulePath 冻结为 Windows PowerShell 原生模块目录（不继承 PowerShell 7/Codex 注入路径）；
          - 脚本首行 $ErrorActionPreference='Stop'，并 Import-Module 原生 Microsoft.PowerShell.Security
            （绝对路径，-ErrorAction Stop）——Get-Acl 加载/执行错误产生非零退出码，不再出现 rc=0 的
            'USER=/|||' 假成功；
          - 输出为带 schema 的 JSON（owner/user/aces[4 字段]）；owner 与当前用户 exact equality；
            ACE 数组非空、每字段非空；'|||' 无法通过 JSON schema；
          - Python 端同时校验退出码、JSON schema 与非空 stderr；任何失败 -> SecretStoreError。
        """
        if os.name != "nt":
            return
        import tempfile

        system_root = os.environ.get("SystemRoot") or r"C:\Windows"
        ps_exe = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        native_modules = str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules")
        if not ps_exe.exists():
            raise SecretStoreError(f"Windows PowerShell 5.1 不存在（fail closed）: {ps_exe}")
        user = self._current_user()
        is_dir = path.is_dir()
        perm = f"{user}:(OI)(CI)(F)" if is_dir else f"{user}:(F)"
        # 宽主体 SID（移除）：SYSTEM/Administrators/Users/Everyone/Authenticated Users
        wide_sids = ["*S-1-5-18", "*S-1-5-32-544", "*S-1-5-32-545",
                     "*S-1-1-0", "*S-1-5-11"]
        try:
            set_cmd = ["icacls", str(path), "/inheritance:r"]
            for sid in wide_sids:
                set_cmd += ["/remove:g", sid]
            set_cmd += ["/grant:r", perm]
            r = subprocess.run(set_cmd, capture_output=True, timeout=60)
            if r.returncode != 0:
                raise SecretStoreError(
                    f"icacls 设置失败（fail closed）: {path} rc={r.returncode} {r.stderr[:200]!r}")
        except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
            raise SecretStoreError(
                f"icacls 不可用/执行失败（fail closed）: {path}（{type(exc).__name__}: {exc}）"
            ) from exc
        # 验证：独立子进程 + 冻结 PSModulePath + JSON 结构化输出
        ps_script = (
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
        script_path: Optional[Path] = None
        sub_env = dict(os.environ)
        sub_env["PSModulePath"] = native_modules  # R78-1：冻结为原生模块路径
        try:
            fd, tmp_name = tempfile.mkstemp(suffix=".ps1", prefix="secretstore_acl_")
            with os.fdopen(fd, "w", encoding="utf-8-sig") as fh:
                fh.write(ps_script)
            script_path = Path(tmp_name)
            v = subprocess.run(
                [str(ps_exe), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(script_path), str(path)],
                capture_output=True, timeout=60, env=sub_env,
            )
        except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
            raise SecretStoreError(
                f"ACL 验证失败（fail closed）: {path}（{type(exc).__name__}: {exc}）"
            ) from exc
        finally:
            if script_path is not None:
                try:
                    os.unlink(script_path)
                except OSError:  # noqa: BLE001
                    pass
        stderr_text = (v.stderr or b"").decode("mbcs", errors="replace").strip()
        if v.returncode != 0 or stderr_text:
            raise SecretStoreError(
                f"ACL 验证失败（fail closed）: {path} rc={v.returncode} stderr={stderr_text[:200]!r}"
            )
        out = (v.stdout or b"").decode("mbcs", errors="replace")
        try:
            data = json.loads(out)
        except (ValueError, TypeError) as exc:  # noqa: BLE001
            raise SecretStoreError(f"ACL 验证输出非 JSON（fail closed）: {path} -> {out[:200]!r}") from exc
        owner = data.get("owner")
        ps_user = data.get("user")
        aces = data.get("aces") or []
        if not owner or not ps_user or owner != ps_user:
            raise SecretStoreError(f"ACL owner 与当前用户不一致（fail closed）: {path} owner={owner!r} user={ps_user!r}")
        if not aces:
            raise SecretStoreError(f"ACL 无 ACE（fail closed）: {path}")
        owner_ok = False
        allowed_prefix = ("CREATOR OWNER", "CREATOR GROUP", "OWNER RIGHTS")
        for ace in aces:
            subj = (ace.get("subject") or "").strip()
            rights = (ace.get("rights") or "").strip()
            atype = (ace.get("type") or "").strip()
            inherited = (ace.get("inherited") or "").strip()
            if not (subj and rights and atype and inherited):
                raise SecretStoreError(f"ACL ACE 字段不全（fail closed）: {path} -> {ace!r}")
            if inherited.lower() != "false":
                raise SecretStoreError(f"ACL 存在继承 ACE（fail closed）: {path} -> {ace!r}")
            if subj.lower() == user.lower() or subj.lower().endswith("\\" + user.lower()):
                if rights == "FullControl" and atype == "Allow":
                    owner_ok = True
            elif subj.upper() in allowed_prefix or subj.startswith("S-1-3-"):
                pass  # 系统固有所有者条目
            else:
                raise SecretStoreError(f"ACL 存在未授权主体（fail closed）: {path} -> {ace!r}")
        if not owner_ok:
            raise SecretStoreError(f"ACL 缺少当前用户 FullControl Allow（fail closed）: {path}")

    @staticmethod
    def _current_user() -> str:
        """当前用户短名（用于 icacls /grant:r <user>）。"""
        import getpass

        return getpass.getuser()

    def _load_or_create_key(self) -> Fernet:
        """R72-5 + R74-3.1：O_CREAT|O_EXCL 原子创建主密钥（0600），并发初始化不互相覆盖。

        FileExists 分支：另一个实例可能已 O_EXCL 创建但尚未写完 key，本实例有界等待重试，
        直到 key 可解析（完整 32-byte urlsafe base64）；超时抛 SecretStoreError。
        """
        key_file = self._dir / MASTER_KEY_FILE
        max_wait_sec = 5.0
        wait_step = 0.01
        waited = 0.0
        try:
            fd = os.open(key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, KEY_MODE)
        except FileExistsError:
            # 等待既有写入完成：有界重试读取可解析 key
            while waited < max_wait_sec:
                raw = key_file.read_bytes().strip()
                try:
                    return Fernet(raw)
                except (ValueError, TypeError):
                    import time

                    time.sleep(wait_step)
                    waited += wait_step
            raise SecretStoreError(f"master.key 写入未在 {max_wait_sec}s 内完成或非法（{key_file}）")
        raw = Fernet.generate_key()
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._chmod(key_file, KEY_MODE)
        self._windows_owner_only(key_file)
        return Fernet(raw)

    def _write_cipher_atomic(self, path: Path, token: bytes) -> None:
        """R72-5：同目录临时文件 O_CREAT|O_EXCL（0600）写密文后 os.replace 原子落位。"""
        tmp = path.with_name(path.name + ".tmp")
        try:
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE)
        except FileExistsError:
            tmp.unlink()
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE)
        with os.fdopen(fd, "wb") as fh:
            fh.write(token)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        self._chmod(path, FILE_MODE)
        self._windows_owner_only(path)

    # ------------------------------------------------------------------ 定位符
    @staticmethod
    def make_locator(
        tenant_id: int,
        account_id: int,
        purpose: str,
        rotation_seq: int,
    ) -> str:
        # R74-2：type() is int 排除 bool（bool 是 int 子类，否则 True 会被当作 1 绕过 grammar）
        if type(tenant_id) is not int or tenant_id <= 0:
            raise SecretStoreError(f"tenant_id 必须为正整数: {tenant_id!r}")
        if type(account_id) is not int or account_id <= 0:
            raise SecretStoreError(f"account_id 必须为正整数: {account_id!r}")
        if purpose not in CREDENTIAL_PURPOSES:
            raise SecretStoreError(f"purpose 非冻结枚举: {purpose!r}")
        if type(rotation_seq) is not int or rotation_seq <= 0:
            raise SecretStoreError(f"rotation_seq 必须为正整数: {rotation_seq!r}")
        loc = f"cred:{tenant_id}:{account_id}:{purpose}:{rotation_seq}:{uuid.uuid4()}"
        if len(loc) > MAX_LOCATOR_LEN:
            raise SecretStoreError(f"定位符超长（>{MAX_LOCATOR_LEN}）：{purpose}")
        return loc

    def _path(self, locator: str) -> Path:
        """R72-4：文件名 = locator 稳定 hash（sha256），无有损别名；get/delete 先 grammar 校验。"""
        digest = hashlib.sha256(locator.encode("utf-8")).hexdigest()
        return self._dir / (digest + ".enc")

    # ------------------------------------------------------------------ 核心
    def put(
        self,
        tenant_id: int,
        account_id: int,
        purpose: str,
        secret: bytes,
        rotation_seq: int = 1,
        expires_at: Optional[str] = None,
    ) -> str:
        locator = self.make_locator(tenant_id, account_id, purpose, rotation_seq)
        # R74-2：写文件前对生成的 locator 再 validate 复核（bool/类型绕过在此拦截，不落孤儿密文）
        validate_locator(locator)
        meta = {
            "locator": locator,
            "tenant_id": tenant_id,
            "account_id": account_id,
            "purpose": purpose,
            "rotation_seq": rotation_seq,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = json.dumps({"meta": meta, "secret_b64": base64.b64encode(secret).decode("ascii")},
                             ensure_ascii=True).encode("utf-8")
        token = self._fernet.encrypt(payload)
        self._write_cipher_atomic(self._path(locator), token)
        return locator

    def get(self, locator: str) -> Tuple[bytes, dict[str, Any]]:
        validate_locator(locator)  # R72-4：拒绝非规范别名
        path = self._path(locator)
        if not path.exists():
            raise SecretNotFoundError(f"定位符不存在: {locator}")
        try:
            payload = json.loads(self._fernet.decrypt(path.read_bytes()))
        except InvalidToken as exc:
            raise SecretNotFoundError(f"密文无法解密（密钥不匹配或损坏）: {locator}") from exc
        meta: dict[str, Any] = payload["meta"]
        # R72-4：密文 payload 绑定原始 locator，解密后复核
        if meta.get("locator") != locator:
            raise SecretNotFoundError(f"密文 locator 绑定不一致（身份错配）: {locator}")
        secret = base64.b64decode(payload["secret_b64"])
        return secret, meta

    def delete(self, locator: str) -> None:
        validate_locator(locator)  # R72-4：拒绝非规范别名
        path = self._path(locator)
        if path.exists():
            secure_delete_file(path)

    def rotate(
        self,
        tenant_id: int,
        account_id: int,
        purpose: str,
        secret: bytes,
        next_seq: int,
        expires_at: Optional[str] = None,
    ) -> str:
        return self.put(tenant_id, account_id, purpose, secret,
                        rotation_seq=next_seq, expires_at=expires_at)


def is_expired(meta: dict[str, Any], now: Optional[datetime] = None) -> bool:
    """过期判定辅助：expires_at 为 ISO8601；None 表示不过期。"""
    raw = meta.get("expires_at")
    if not raw:
        return False
    exp = datetime.fromisoformat(raw)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now >= exp


def secure_delete_file(path: Path) -> None:
    """尽力覆盖后删除（凭证文件销毁辅助；非强保证）。"""
    if path.exists():
        try:
            size = path.stat().st_size
            with open(path, "r+b") as fh:
                fh.write(b"\x00" * size)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:  # noqa: BLE001
            pass
        path.unlink()
