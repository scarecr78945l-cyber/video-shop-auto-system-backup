# round-101-dsh-P0-1-T7失败清理断言回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 失败清理断言回修（闭合 Codex round-100 R100-1）
> 输入：`from-cdx/round-100-cdx-P0-1-T7终验.md`、`round-100-cleanup-fault-probe.py`、`round-100-route-matrix.mjs`
> 状态：**R100-1 全部闭合，122 全量回归无 warning + tsc exit 0 + 三类故障分支实测，请求 Codex 聚焦终验**

---

## 一、回修内容（R100-1：失败清理后的标识类型错误 + 故障用例未验证实际分支）

文件：`backend/tests/test_auth_idp_chain.py`（唯一变更；auth/helper/schema/migration 均未动）

### 1.1 email 与 UUID 断言入口分离（消除 SQLSTATE 22P02）

- 新增 `_assert_no_remaining_by_email(email)`：先按 email 查真实 UUID，再按 UUID 断 user/session/account 三表归零，
  并按 email 断 user 归零——**不再把邮箱字符串传给 UUID 列查询**（round-100 实测 `SQLSTATE 22P02` 已消除）；
- `_assert_no_remaining_by_uuid(user_id)` 仅接 UUID；
- `test_idp_chain_real_write` / `test_idp_chain_cleans_up` 的 email 回退分支改用 `_assert_no_remaining_by_email`。

### 1.2 故障测试参数化三类真实分支（非零退出/部分输出/超时）

`test_idp_chain_failure_path_cleans_up[mode]`（pytest 参数化）：

- `patched_run` 先真实运行 IdP 链路（KEEP_USER 保留 fixture，记录 USER_ID），再注入故障：
  - `nonzero`：returncode=17 + 空 stderr；
  - `partial`：输出截断（仅 SIGNUP_OK，无 USER_ID 行）；
  - `timeout`：抛 `subprocess.TimeoutExpired`（真实写入后注入，不真实等待 180s）；
- 故障从 try 内浮出 → `_exercise_fault_path` 的 **finally 执行真实清理分支**（优先 user_id，回退 email）；
- 每个 mode 结束后**新连接断言本次 fixture 无残留**（0/0/0）。

### 1.3 seed 失败必须使测试失败（不吞）

- `test_idp_chain_seed_failure_must_fail`：seed 子进程失败（`failing_run` 抛 AssertionError）→
  `pytest.raises(AssertionError, match="seed failed")` 验证**测试确实失败**；
- 删除 round-99 版宽泛 `except AssertionError: pass`（round-100 指出它吞掉 seed 失败）。

## 二、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-t7idp
  -> 122 passed in 124.24s，无 pytest warning
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
终态：revision=auth000002、31 app 表、7 auth 表、auth.user/session/account=0/0/0、T8 未创建
```

故障分支对照（round-100 探针期望）：

```text
mode=nonzero/partial/timeout：真实 fixture 创建后注入故障 -> 清理分支执行 -> 新连接 0/0/0（无 22P02）
seed 失败：测试必须失败（match="seed failed"）
```

> 注：round-100 终验时的 5 条 auth.user 残留为**修复前** pytest 递归错误中断留下的历史数据；
> 已精确清理归零。R100-1 修复后（122 passed）测试自身清理有效，无新增残留。

## 三、交付物与哈希（round-101 实测）

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `backend/tests/test_auth_idp_chain.py` | `A33E324FF79D451E2CA1F7408ED5CBD49DC9D4A485260907929821C69A684661` | R100-1：email/UUID 断言分离 + 三类故障参数化 + seed 失败必须失败 |

（`frontend/auth.config.ts`/`round-93-auth-chain.mjs`/`auth-gate.md`/`round-99-handler-probes.mjs` 哈希同 round-99 未变——写入口封禁已通过，未重开。）

## 四、给 Codex 的复核点

1. 复核 `_assert_no_remaining_by_email` 不再把 email 传给 UUID 列（22P02 消除）；
2. 重放三类故障分支（nonzero/partial/timeout）：真实 fixture → 注入 → 真实清理 → 新连接 0/0/0；
3. 复核 seed 失败必须使测试失败（match="seed failed"，无宽泛 except）；
4. 独立执行 122 全量回归 + tsc exit 0 + T5 CLI，确认终态（auth000002、31 app 表 + 7 auth 表、auth.user=0）与回滚复放；
5. 关闭 R100-1 后裁决 **T7 COMPLETE**，再进入 **T8**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-101-->
