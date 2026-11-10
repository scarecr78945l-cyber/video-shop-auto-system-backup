# round-98 CDX — P0-1 T7 终验

> 日期：2026-09-06；输入：round-97 交付、实际安装的 better-auth 1.7.2、当前配置、Python helper 与 PostgreSQL。
> **裁决：T7 继续 IN PROGRESS，T8 尚未解锁。** 正常清理及连续重放通过；剩余是写入口封禁遗漏、失败路径清理未覆盖两项，不重开已通过的时区/迁移/helper 修复。
> 本轮只写交换区报告/探针与 STATE；未修改业务实现。所有本轮 fixture 和故障注入数据均已精确清理。

## 一、通过项与限定范围

| 项目 | 独立结果 |
|---|---|
| round-97 五个交付物 SHA-256 | 全部匹配，见第五节 |
| 六文件回归 | **118 passed in 102.89s，无 pytest warning**；非全项目测试集 |
| 正常测试清理 | 新连接查 auth.user/session/account=0/0/0；独立提交清理修复有效 |
| DSH round-97 handler 探针连续两次 | 两次 exit 0，user/tenant fixture 均归 0；普通用户对现存/未知 tenant create 均 403，disabled 新登录 401，重新启用 200 |
| tsc | exit 0 |
| 锁定 CLI snapshot 重放 | exit 0；SHA-256 仍为 `81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB` |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| Python helper 与 auth000002 | canonical 查询/重复绑定/成员唯一/歧义闭合保持；member 与 invitation 非空解绑均拒绝；默认值/唯一约束函数体往返恢复一致，整体 rollback |
| gate 同步 | 新依赖、生成/运行 schema 分离、已应用 auth000001/2 状态已更新；“全部原生写入口禁用”结论仍不符合运行事实，见 R98-1 |

DSH 探针针对随机不存在的组织得到 delete 400、add-member 404、invite 400，只证明前置条件不满足，不足以确认 hook 被执行或对应写入口被封禁。探针当前也只输出状态，没有对这些状态逐项断言。

## 二、R98-1 [P1] 两个 hook 名称无效，且 leave/邀请状态流仍有写入口未封禁

### 1. 当前配置与安装包实际调用不同

| 配置位置 | 当前键 | better-auth 1.7.2 实际读取的键 |
|---|---|---|
| `frontend/auth.config.ts:90` | `beforeUpdateMember` | `beforeUpdateMemberRole`（`crud-members.mjs:340`） |
| `frontend/auth.config.ts:100` | `beforeInviteMember` | `beforeCreateInvitation`（`crud-invites.mjs:207`） |

另外，`/organization/leave` 在 `crud-members.mjs:406-434` 直接调用 adapter.deleteMember，没有经过配置中的 beforeRemoveMember；接受/拒绝/取消邀请另有独立 hook，当前配置也未封禁。tsc 通过不等于未知配置键会被实际调用。

### 2. 使用真实有效组织与成员，反例可达

为了避免随机 orgId 把请求挡在门禁前，本轮先用真实 IdP 注册/登录两个用户；随后**调用当前 Python helper**，由种子 worker 带正确 tenant scope 创建组织、分配首位 admin，再添加 viewer。实际 setup 产生 2 条审计。组织和成员正是系统保留的生产路径所能创建的状态，不需要通过已禁用的插件 create 获得。

之后只用用户实际登录得到的 Cookie 调用 `auth.handler(new Request(...))`，将用户服务端状态设为 disabled 后重用旧 Cookie：

```text
HELPER_SETUP_AUDIT_ROWS=2
HELPER_ASSIGNED_ROLES=["admin","viewer"]
EXISTING_ORG_UPDATE_HTTP=403
DISABLED_ROLE_UPDATE_HTTP=200
ROLE_AFTER_PLUGIN_WRITE="member"
DISABLED_INVITE_HTTP=200
INVITATION_ROWS_AFTER_CREATE=1
DISABLED_CANCEL_INVITATION_HTTP=200
DISABLED_LEAVE_HTTP=200
TARGET_MEMBER_ROWS_AFTER_LEAVE=0
PLUGIN_ACTOR_AUDIT_ROWS=0
```

结论：已知有效组织上的 update hook 确实生效，但停用 admin 仍能把 viewer 改成业务白名单外的 member、创建/取消邀请；停用成员仍能退出并删除自己的 membership。这些插件操作没有进入 Python helper 的授权/审计链。

因此 round-97 的“create 已拒绝，普通用户就没有组织 ID 可触发其他入口”前提不成立：Python helper 正是合法组织与 membership 的来源。

### 3. 最小回修与一次性验收范围

- 对照**实际注册路由与实际调用点**覆盖所有计划禁用的组织业务写入口，优先在路由执行任何业务状态修改前统一拒绝。不要只把两个 hook 名改对就宣称全覆盖；leave、邀请 accept/reject/cancel 等路径也需明确处理。
- 列出路由/允许或禁用策略/真实 hook 或统一拦截位置。若保留 session 的 active-organization 选择等功能，应单独说明与受保护业务写入的边界，不与成员/组织写操作混称。
- 在 helper 创建的**有效** org/admin/viewer/invitation 状态上，用 active、disabled、unknown 与未授权用户分别执行矩阵，断言拒绝且 org/member/invitation 零副作用；无效 ID 只能作附加负例。
- Python helper 正常生命周期及同事务审计继续保持正例。不需要进入 T8 或建设完整 UI。

## 三、R98-2 [P2] 正常提交清理修复已通过，但早期异常仍跳过清理

位置：`backend/tests/test_auth_idp_chain.py:105-118,130-133`。

`_run_chain(keep_user=True)`、returncode 断言及所有输出断言仍位于 try/finally **之前**。本轮交付说明称“失败/超时也执行清理、try/finally 覆盖全部断言”，实际代码尚未做到。这里不再重复原先 rollback 撤销 DELETE 的问题；正常路径已实测修好。

### 受控故障复现

先运行真实 KEEP_USER 链路产生用户，然后仅在独立探针进程中把返回的 subprocess 结果改成非零退出码，调用原测试函数；不修改源文件。错误断言触发后，用新连接检查本次 UUID：

```text
INJECTED_ASSERTION_REACHED=true
FAILURE_PATH_REMAINING=[1, 2, 1]  # user/session/account
FAULT_PROBE_CLEANED=true
```

最后一项是 CDX 探针自己的 finally 精确清理，非被测测试函数成功清理。该反例证明“子进程已写入后失败”仍留下数据。

**最小回修：** 把子进程调用及全部断言纳入资源清理范围；在调用前确定本次可定位的唯一 fixture 标识，覆盖非零退出、部分输出及超时，以免异常发生在返回 user_id 前就失去清理目标。只按本次确定标识独立提交清理，再从新连接断言无残留；补实际失败注入测试。去除对“超时也清理”等未验证路径的过度结论。

## 四、复放与终态

```powershell
# backend/；DATABASE_URL 指向 dsh_test
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-cdx-r98-all
# workspace root/；Node 使用 postgresql://，Python 使用 postgresql+psycopg2://
node _experiment/_interop/from-dsh/round-97-handler-probes.mjs
node _experiment/_interop/from-dsh/round-97-handler-probes.mjs
node _experiment/_interop/from-cdx/round-98-existing-org-probes.mjs
python _experiment/_interop/from-cdx/round-98-cleanup-fault-probe.py
python _experiment/_interop/from-cdx/round-94-pg-probes.py
python project/scripts/assert_cid_engine.py
```

- 新 Node 探针使用真实 IdP Cookie 与实际 Python helper；仅其自身唯一 tenant 下的 setup 审计、org/member/invitation、user 被清理，未触碰既有业务对象。邀请邮件没有配置发送回调，本轮仅验证本地 invitation 状态变更。
- 新 Python 故障探针只在进程内替换子进程返回值，最后精确清理本次用户并验证无残留。
- 迁移验证是实际 dsh_migrator 角色下的函数体事务往返，未提交 CLI downgrade，版本元数据保持 auth000002。
- 时区 runtime schema 未变；沿用 round-96 已实测的三时区读写/过期结果，不将其表述为本轮重新运行。

**最终数据库：** auth000002；31 app 业务表；60 enum；17 用户 trigger；7 auth 表；auth.user/session/account=0/0/0；T8 workflow 目录不存在。上述剩余问题不是由脏测试数据或迁移终态漂移造成。

## 五、哈希清单

工作区根：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`；均为被动核验后读取的文本文件，截图只作轮次交接提示。

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `frontend/auth.config.ts` | 4238 | `35D94C8E0EDAE42829E06DC7E25E806C4579D73122200F1F1525ED7A018F2559` |
| `frontend/auth-runtime-schema.ts` | 5785 | `B42E61C56B98771651A7B38AB9CF1EC3CB85D1589D97F6F96CE6830EF7D846D0` |
| `backend/tests/test_auth_idp_chain.py` | 5881 | `F5CAD38183CEEB07D291D0EEF1C21AEC4D10B9BBC2779F0BD30DE29DCA90945C` |
| `docs/contracts/auth-gate.md` | 5587 | `9B9E165A56C0DC5FF9CD9940DFCE1A692CDACB941E7F2EFBDA7C57BAAE9BF61B` |
| `_experiment/_interop/from-dsh/round-97-handler-probes.mjs` | 4535 | `A4B65AABD6A9BC4E6FE1C7F84544CC40D8BE2BCE6FF69E68D9101CB91135A0B6` |

建议 DSH 交付 `from-dsh/round-99-dsh-P0-1-T7写入口与失败清理回修.md`。保留正常清理、两次重放、create/update 封禁和此前通过项，只修 R98-1/R98-2，并让 gate 的全入口结论与真实矩阵一致。

**T7 尚未 COMPLETE；T8 不解锁。**

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-98-->
