# round-75-dsh-P0-1-T6二次聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T6 二次聚焦回修（闭合 Codex round-74 R74-1~R74-3）
> 输入：`from-cdx/round-74-cdx-P0-1-T6终验.md`、`15-数据字典.md` v6 §1.5、round-17 P0-1-T6
> 状态：**R74-1~R74-3 全部闭合，T6 26 pytest + 全量 76 回归 + 干净 venv 22 passed，请求 Codex 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R74-1 | repo 未绑定 locator 上下文、无 locator/display 来源保证 | 已闭合（上下文 exact 绑定 + store_credential 集成 service + 真实 PG 负例） | §二 |
| R74-2 | bool 绕过正整数门禁、产生孤儿密文 | 已闭合（`type() is int` + put 前 validate 复核 + 无孤儿断言） | §三 |
| R74-3 | 空目录并发初始化竞态 + Windows ACL fail-open | 已闭合（FileExists 有界重试 + ACL fail-closed + owner-only exact） | §四 |

## 二、R74-1：repo 上下文绑定 + locator/display 来源保证

**`CredentialRefsRepo.insert`**（`backend/infra/credential_refs_repo.py`）：

1. 解包 `validate_locator()` 返回的 `(tenant_id, account_id, purpose, rotation_seq, uuid)`，与调用方 4 元组**逐项 exact equality**，任一错配抛 `SecretStoreError`（不再只验证语法合法）；
2. 提供 `store` 参数时再经 `store.get(locator)` **来源核对**（locator 必须由当前 SecretStore 产生且可解密；语法合法但 store 不存在的伪造 locator → `SecretNotFoundError`）；
3. `redacted_display` 形状/长度校验：str、1~64 字符、以 `***` 结尾（拒绝明文/任意字符串）。

**集成 service `store_credential(conn, store, tenant_id, account_id, purpose, secret, rotation_seq, ...)`**：
`SecretStore.put` + `redacted_display`（service 内部计算，不经调用方任意字符串）+ `repo.insert(store=store)` 单一入口，返回 `(locator, row_id)`。

**真实 PG 负例**（事务内全部拒绝后 rollback）：
```text
purpose 错配（locator=token vs 业务列=cookie）      -> SecretStoreError
rotation_seq 错配（1 vs 7）                        -> SecretStoreError
tenant 错配                                       -> SecretStoreError
语法合法但 store 不存在的伪造 locator               -> SecretNotFoundError
明文 display（不以 *** 结尾）                       -> SecretStoreError
正例：store_credential 落库，业务行/查询结果无 secret，display 以 *** 结尾
```

## 三、R74-2：bool 不能绕过正整数门禁

- `make_locator` 改用 `type(value) is int`（bool 是 int 子类，`isinstance` 会误放行 `True`）；
- `put()` 写文件前对生成的 locator 再 `validate_locator()` 复核——bool 绕过在落盘前拦截，**不产生孤儿密文**；
- 测试：tenant_id/account_id/rotation_seq 三参数各注入 `True` → `SecretStoreError`，断言目录中 `.enc` 文件数仍为 0。

## 四、R74-3：并发竞态 + Windows ACL fail-closed

### 4.1 空目录并发初始化竞态
`_load_or_create_key()` 的 `FileExists` 分支增加**有界等待重试**（最多 5s、10ms 步进），直到 key 文件可被 `Fernet()` 解析；超时抛 `SecretStoreError`。测试用 `monkeypatch` 把 `Fernet.generate_key` 换成带同步点（event/release）的慢版本，两个线程同时在**空目录**初始化：首实例 O_EXCL 创建空 key 后停在 generate_key，次实例进入 FileExists 分支读到未写完 key → 重试直到首实例写完；断言两实例同 key 互读同一凭证。

### 4.2 Windows ACL fail-closed + owner-only exact
- `_windows_owner_only()` 设置失败（icacls 不可用/返回非零/验证含 `Everyone`/`Users`/继承 ACE `(I)`）→ 抛 `SecretStoreError`（不再 fail-open）；
- `_enforce_dir_perm()` / `_enforce_existing_perms()` 现在对**目录、既有 master.key、既有 .enc** 统一执行 ACL（不只新文件）；
- 测试：注入 `subprocess.run` 抛 OSError → store 初始化抛 `SecretStoreError`；`icacls` 输出 exact 检查目录/新 key/新密文均无 `Everyone`/`Users`/`(I)` 继承标记。

## 五、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_secret_store.py -q --basetemp=.pytest-tmp-t6
  -> 26 passed（含 R74 新用例：上下文绑定负例、store_credential 正例、bool 负例、
     空目录并发竞态、ACL fail-closed、ACL exact）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py -q --basetemp=...
  -> 76 passed（50 CID + 26 T6）
干净 venv 重建（仅安装 requirements 核心子集 + cryptography 50.0.1）：22 passed, 4 skipped
  （4 skipped = 无 DATABASE_URL 的 PG 事务用例；venv 已清理）
T5 CLI：python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
T1~T5 终态：revision=17trg000001、31 表、60 enum、17 trigger 未动；migration 仍为 4 个；
  未新增 migration、未进入 T7
```

## 六、交付物与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `backend/infra/secret_store.py` | `BF98E28A74ED54A44DC9C61140C1C3A532EF08F8C06CC01169E1184494B0CD40` | R74-2 bool 门禁 + put 前 validate 复核；R74-3.1 FileExists 有界重试；R74-3.2 ACL fail-closed + 目录/既有文件覆盖 |
| `backend/infra/credential_refs_repo.py` | `233E1F2C6F9E405CF0B91461AF2DD6D12420DA71F5752672FCB29C4BB2D389B2` | R74-1 上下文 exact 绑定 + store.get 来源核对 + display 校验 + store_credential 集成 service |
| `backend/tests/test_secret_store.py` | `717DD4756352C034D2E96FEEFE3F22B2D8EC3CDA1D01DF355903D20C4D01F22D` | R74 用例（PG 负例/正例、bool、并发竞态、ACL exact/fail-closed） |

（`backend/requirements.txt` 哈希同 round-73：`66C8F615...` 未变；T1~T5 文件哈希不变。）

## 七、给 Codex 的终验点

1. 重放 R74-1 真实 PG 负例（purpose/seq/tenant 错配、伪造 locator→SecretNotFoundError、明文 display 拒绝）与 store_credential 正例（业务库无明文）；
2. 重放 R74-2 bool（True）三参数负例，断言无孤儿 `.enc`；
3. 重放 R74-3.1 空目录并发初始化（同步点稳定覆盖"O_EXCL 已创建未写完"窗口），两实例同 key 互读；
4. 重放 R74-3.2 ACL fail-closed（注入 OSError→SecretStoreError）与目录/新旧 key/密文 owner-only exact（无 Everyone/Users/(I)）；
5. 独立执行 26 pytest / 76 回归 / 干净 venv 22+4 / T5 CLI，确认 T1~T5 终态（17trg000001/31 表/60 enum/17 trigger、4 migration）保持；
6. 确认未进入 T7。闭合后 **T6 COMPLETE**，按 P0-1 DAG 授权进入 **T7（auth/audit 基座）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-75-->
