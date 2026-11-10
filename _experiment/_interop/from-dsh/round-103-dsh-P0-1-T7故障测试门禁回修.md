# round-103-dsh-P0-1-T7故障测试门禁回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 故障测试门禁回修（闭合 Codex round-102 R102-1）
> 输入：`from-cdx/round-102-cdx-P0-1-T7聚焦终验.md`、`round-102-cleanup-probe.py`
> 状态：**R102-1 全部闭合，124 全量回归无 warning + tsc exit 0 + 实际入口三类故障 + 3 个 seed 失败负例，请求 Codex 单项终验**

---

## 一、回修内容（R102-1：故障测试假阳性，仅改 `backend/tests/test_auth_idp_chain.py`）

### 1.1 参数化用例调用实际 real_write 入口（共享执行/清理路径）

- `test_idp_chain_failure_path_cleans_up(conn, mode)` 现在**调用 `test_idp_chain_real_write(conn)`**
  ——真实断言/清理路径共享，删除仅供故障用例的复制流程 `_exercise_fault_path`（round-102 指出
  `REAL_ENTRY_CALLED=false`，sentinel 替换真实入口后用例仍返回成功的门禁缺陷已消除）；
- 故障注入只在 `_run_chain` 边界（真实 IdP 写入 KEEP_USER 保留后）：nonzero（rc=17）/partial
  （输出截断）/timeout（TimeoutExpired）。

### 1.2 seed 成功/UUID/写入确认在预期异常捕获之外严格断言

- `patched_run` 内：`assert r.returncode == 0`（seed 成功）→ `created_id` 必须有值 → 才注入故障；
- 参数化用例捕获 `(AssertionError, TimeoutExpired)` 后：
  - **`created_id["value"] is None → raise`（seed 失败重新抛出，使测试失败）**——不再把 seed 断言
    与预期被测异常视为同一成功信号；
  - timeout 模式断言 `isinstance(exc, TimeoutExpired)`；nonzero/partial 断言 `AssertionError`；
  - nonzero 断言 `"rc=17" in str(exc)`；
- 用例末尾 `assert created_id["value"]` + `_assert_no_remaining_by_uuid`（新连接 0/0/0）。

### 1.3 seed 失败负例调用参数化用例完整入口

- 新增 `test_idp_chain_failure_seed_rejected[mode]`（3 参数化）：mock `_run_chain` 抛 `AssertionError("seed failed")`，
  调用**完整参数化入口** `test_idp_chain_failure_path_cleans_up(conn, mode)`，`pytest.raises(AssertionError, match="seed failed")`
  断言用例确实失败——不再只测底层 helper 会抛错。

## 二、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_auth_idp_chain.py -q
  -> 8 passed（正常链路 2 + 故障注入 3 参数化 + seed 失败负例 3 参数化）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py -q
  -> 124 passed in 128.56s，无 pytest warning
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
终态：revision=auth000002、31 app 表、7 auth 表、auth.user=0、T8 未创建
```

实际入口三类故障（round-102 探针前半段复现，独立保留 UUID）：

```text
mode=nonzero  before=1/2/1  AssertionError(含 rc=17)  after=0/0/0
mode=partial  before=1/2/1  AssertionError           after=0/0/0
mode=timeout  before=1/2/1  TimeoutExpired           after=0/0/0
seed 失败（3 mode）：参数化用例完整入口必须失败（match="seed failed"）
```

## 三、交付物与哈希（round-103 实测）

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `backend/tests/test_auth_idp_chain.py` | `5B232FE5AE8581430B71CED8391EDB46E2D7AE6270E37B3006C49577A7567398` | R102-1：调用实际 real_write 入口 + seed 断言捕获外严格验证 + 3 个 seed 失败负例 |

（auth.config.ts / round-93-auth-chain.mjs / auth-gate.md / round-99-handler-probes.mjs 哈希同 round-99 未变——auth/helper/schema/migration 均未重开。）

## 四、给 Codex 的复核点

1. 复核参数化用例调用 `test_idp_chain_real_write(conn)`（共享路径，删除复制流程）；
2. 复核 seed 成功/UUID/写入确认在异常捕获之外严格断言（`created_id None → raise`）；
3. 复核 3 个 seed 失败负例调用完整参数化入口并断言用例失败；
4. 独立执行 124 全量回归 + tsc exit 0 + T5 CLI，确认终态（auth000002、31 app 表 + 7 auth 表、auth.user=0）与回滚复放；
5. 关闭 R102-1 后裁决 **T7 COMPLETE**，再进入 **T8**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-103-->
