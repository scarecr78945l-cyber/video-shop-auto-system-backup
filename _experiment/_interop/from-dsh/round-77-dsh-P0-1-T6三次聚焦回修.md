# round-77-dsh-P0-1-T6三次聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T6 三次聚焦回修（闭合 Codex round-76 R76-1/R76-2）
> 输入：`from-cdx/round-76-cdx-P0-1-T6二次终验.md`、`15-数据字典.md` v6 §1.5、round-17 P0-1-T6
> 状态：**R76-1/R76-2 全部闭合，T6 28 pytest + 全量 78 回归 + 干净 venv 24+4 PASS，请求 Codex 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R76-1 | repo 默认写入路径绕过 SecretStore 来源/display 绑定 | 已闭合（store 必传 + 无条件来源核对 + meta 四元组复核 + display 内部计算） | §二 |
| R76-2 | ACL 路径文本误判 + 其他显式主体未清除 | 已闭合（icacls 结构化设置 + Get-Acl exact-set 验证 + 宽主体 SID 移除） | §三 |

## 二、R76-1：repository 来源/display 绑定（强制 store）

**`CredentialRefsRepo.insert`（`backend/infra/credential_refs_repo.py`）**：

1. **`store` 改为必传且非空**（参数默认值删除，`store=None` 显式拒绝）——「只接收 SecretStore 产生的 locator」成为方法级契约；
2. **无条件 `secret, meta = store.get(locator)`**：语法合法但 store 中不存在的伪造 locator → `SecretNotFoundError`；
3. **解密 meta 四元组复核**：`meta.tenant_id/account_id/purpose/rotation_seq` 与调用方逐项 exact equality；
4. **display 由 secret 内部计算**：`display = _redact_display(secret)`（调用方不再传任意字符串，`FULL_SECRET_LEAK***` 即使形状合法也无法进入业务表）；`redacted_display` 参数已删除。

**集成 service `store_credential()`**：`SecretStore.put` + `repo.insert(store=store)` 单一入口；所有真实 PG 写入测试统一走该路径或显式传 `store`。

**真实 PG 负例**（事务内全部拒绝后 rollback）：
```text
store=None                       -> SecretStoreError
purpose/rotation_seq/tenant 错配 -> SecretStoreError
伪造 locator（store.get）         -> SecretNotFoundError
redacted_display 参数已删除        -> TypeError（不再接受任意 display）
正例：store_credential 落库，业务行/查询无 secret，display == redacted_display(secret)
```

## 三、R76-2：Windows ACL 结构化设置 + exact-set 验证

### 3.1 设置（icacls，不再用 .NET Set-Acl——目录需 SeSecurityPrivilege 会失败）

```text
icacls <path> /inheritance:r                          # 移除继承
icacls <path> /remove:g *S-1-5-18                     # SYSTEM
icacls <path> /remove:g *S-1-5-32-544                 # Administrators
icacls <path> /remove:g *S-1-5-32-545                 # Users
icacls <path> /remove:g *S-1-1-0                      # Everyone
icacls <path> /remove:g *S-1-5-11                     # Authenticated Users
icacls <path> /grant:r <user>:(OI)(CI)(F)             # 目录
icacls <path> /grant:r <user>:(F)                     # 文件
```

### 3.2 验证（PowerShell Get-Acl 结构化解析，不再对整段 stdout 做子串匹配）

- 解析每行 ACE `subject|rights|type|inherited`（路径首行不参与主体判定，`C:\Users\...` 不再误判）；
- 每条 ACE `IsInherited=False`；
- 主体集合 ⊆ {当前用户, OWNER RIGHTS, CREATOR OWNER, CREATOR GROUP, S-1-3-*}（系统固有允许项）；
- 当前用户存在 `FullControl Allow`；
- 任一 icacls/验证失败或出现未授权主体 → `SecretStoreError`（fail closed）。

### 3.3 测试

```text
test_windows_acl_users_path_no_false_positive：
  系统临时目录（C:\Users\...）路径含 Users，不误判；ACL exact-set PASS
test_windows_acl_second_subject_fail_closed：
  注入 SYSTEM:(F) 后重新初始化，SYSTEM 被清除、owner-only exact 恢复
test_windows_acl_exact_owner_only / best_effort：
  目录/新 key/新密文 Get-Acl 结构化验证（无继承、无宽主体、当前用户 FullControl）
test_windows_acl_fail_closed：注入 OSError -> SecretStoreError
```

## 四、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_secret_store.py -q --basetemp=.pytest-tmp-t6
  -> 28 passed（含 R76-1 负例、R76-2 ACL 结构化用例）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py -q --basetemp=...
  -> 78 passed（50 CID + 28 T6）
干净 venv 重建（无 DATABASE_URL，PG 用例跳过）：24 passed, 4 skipped
T5 CLI：python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
T1~T5 终态：revision=17trg000001、31 表、60 enum、17 trigger 未动；migration 仍为 4 个；
  未新增 migration、未进入 T7
```

> 注：round-76 干净 venv 为 22+4；round-77 新增 R76 用例后为 24+4（4 skipped = 无 DATABASE_URL 的 PG 事务用例）。

## 五、交付物与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `backend/infra/secret_store.py` | `36A33B9DA038262B56B06A0E9320750C1E7258CA9080ED25ED3937A09164A91C` | R76-2：icacls 结构化设置（宽主体 SID 移除）+ Get-Acl exact-set 验证 + fail closed |
| `backend/infra/credential_refs_repo.py` | `2C8AC6B21570BF6B4BF17F5F2AF7DB12958E0645D4E987A0F3BA007A5871CE3A` | R76-1：store 必传 + 无条件 store.get + meta 四元组复核 + display 内部计算 |
| `backend/tests/test_secret_store.py` | `12CE6D3D5776DBE6EA223CDDAD9C69E186755F1FFEED8220DE6A7E23A0E26729` | R76 用例（store=None/伪造/display 删除、C:\Users 路径、SYSTEM 注入清除、ACL exact） |

（`backend/requirements.txt` 哈希同 round-73：`66C8F615...` 未变；T1~T5 文件哈希不变。）

## 六、给 Codex 的终验点

1. 重放 R76-1 负例（store=None → SecretStoreError、伪造 locator → SecretNotFoundError、meta 四元组错配、`redacted_display` 参数已删除）与 store_credential 正例（display == redacted_display(secret)）；
2. 重放 R76-2 C:\Users 路径正例（不误判）与 SYSTEM 注入清除用例（owner-only exact）；
3. 独立执行 28 pytest / 78 回归 / 干净 venv 24+4 / T5 CLI，确认 T1~T5 终态（17trg000001/31 表/60 enum/17 trigger、4 migration）保持；
4. 确认未进入 T7。闭合后 **T6 COMPLETE**，按 P0-1 DAG 授权进入 **T7（auth/audit 基座）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-77-->
