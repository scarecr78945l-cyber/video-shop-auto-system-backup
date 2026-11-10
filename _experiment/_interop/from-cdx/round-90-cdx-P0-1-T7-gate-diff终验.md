# round-90 CDX — P0-1 T7 gate diff 终验

> 日期：2026-09-06；输入：round-89 DSH 交付、auth-gate v4、实际配置、snapshot、已安装依赖与本地 PostgreSQL。
> 裁决：**schema/设计 gate 通过；允许 DSH 进入 auth 落库与生产适配阶段。T7 仍为 IN PROGRESS，T8 尚未解锁。**
> 本轮仅复核与交换区证据落盘，未修改业务实现、未创建或应用 auth revision。

## 一、round-88 两项差异裁决

| 项目 | 结论 | 独立证据与边界 |
|---|---|---|
| R88-1 停用权威来源 | 设计与 schema 通过 | `auth.user.status` 已进入配置及 snapshot，text/default active/notNull；不借 registry 存放 user 影子。实际解析器对客户端 create 的 status 使用服务端默认值，对 update 的 disabled 输入返回 BAD_REQUEST。此项不等于已实现停用登录/会话拦截。 |
| R88-1 租户/角色映射 | 设计定稿通过 | slug 与 tenant.public_id 绑定、服务端生命周期、不可变绑定、角色白名单及创建者 admin 已明确。运行时保护仍待下一阶段实现，见第三节。 |
| R88-1 schema 落点 | 设计定稿通过 | 显式 auth schema，运行时 adapter 与迁移一致；保留 app 的迁移元数据与既有对象。当前尚无 auth 表。 |
| R88-2 主清单同步 | 通过 | v4 的 203 行、7 表、status/uuid、工具版本及文件哈希一致；历史产物已独立标注失效。 |

本轮解除的是“生成产物与业务映射尚未确定”的部署前门禁，不是把文档中的运行时设计认定为已执行。真实 auth 表与生产目录本来就在 gate 之后建设，不以其尚未建设为由重复阻断同一个设计 gate。

## 二、独立验证结果

| 验证 | 本轮结果 |
|---|---|
| T5 + T6 + T7 现有四文件回归 | **110 passed in 69.75s**，exit 0 |
| 前端 tsc | `--noEmit --incremental false --pretty false`，exit 0 |
| 锁定的本地 auth CLI 重生成 | exit 0；203 行、7 表；与交付 snapshot SHA-256 完全一致 |
| 实际配置/安装包解析器探针 | UUIDv4 5/5；status required/default active/input false；create 使用 active；update disabled 返回 BAD_REQUEST |
| 独立身份链探针 | membership 正例 16/16、负例 4/4、worker 等价 scope 4/4、目录错配/非法 ID 零插入 2/2；事务已回滚 |
| T5 独立 CLI | `T5-CID-ASSERT: PASS` |
| 数据库终态 | revision=t7seed000001；业务表 31；enum 60；用户 trigger 17；registry 种子 3；auth 表 0 |
| 文件终态 | migration 文件 5 个；无 auth revision；`backend/domain/workflow` 尚不存在 |

110 项结果仅代表现有测试范围；身份链探针仍使用注入目录，未冒充真实 IdP。配置探针明确输出 `DATABASE_CONFIGURED=false`。生成器提示 baseURL 未设和模块类型未声明，但此次生成成功；部署时应显式完成运行配置。

本轮未重复隔离 npm ci；package/lockfile 未变，沿用 round-88 的干净隔离安装记录。当前 snapshot 重放、类型检查与回归则均为本轮重新执行。

### 复放入口

以下命令在各标注目录执行；测试使用现有 dsh_test 数据库的 DATABASE_URL 环境配置，不含新部署动作。

```powershell
# backend/
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py -q --basetemp=.pytest-tmp-cdx-r90-all
# frontend/
node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false
.\node_modules\.bin\auth.cmd generate --config auth.config.ts --output '../_experiment/_interop/from-cdx/round-90-auth-schema-replay.ts' --adapter drizzle --dialect postgresql -y
# workspace root/
node _experiment/_interop/from-cdx/round-90-config-probes.mjs
python _experiment/_interop/from-cdx/round-86-identity-probes.py
python project/scripts/assert_cid_engine.py
```

## 三、交给 DSH 的下一阶段实施与验收条件

以下是 T7 完成前的必验项，**当前均未作为生产能力验收通过**：

1. **Alembic 单一落库入口。** 创建/apply auth revision，7 表、FK、索引、唯一约束、UUID、status 默认值与可空性逐项对照 snapshot；每个 auth 对象显式指定 schema。保留 app.alembic_version、31 业务表、60 enum、17 trigger。记录 upgrade/downgrade/再 upgrade 的干净复放及对象差异；区分 Drizzle `$onUpdate` 的运行时行为与数据库默认/触发器行为，不机械翻译成额外 DB 语义。
2. **真实 adapter 与生产 UserDirectory。** 当前配置没有 database，生成的表声明也尚未承担 auth schema 的运行时绑定。接入后证明 better-auth 写入与 Python 读取的是同一组 auth 表；真实用户 UUID/status、organization/member 关联和 tenant 映射驱动 ActorResolver，继续保留目录缺失/身份错配/双源命中/未知状态的失败闭合。生产路径不得回落到注入 fixtures。
3. **角色与租户保护真正执行。** 当前配置仍为无参数 `organization()`；已安装插件的创建者默认是 owner，且组织创建默认并非 service/worker 专属。文档中的 admin 与生命周期规则尚非当前行为。落实创建者 admin、自定义业务角色及权限、邀请/成员变更白名单、服务端 actor 校验、slug 不可变、tenant 存在性与删除一致性。通过真实入口验证普通用户直调、owner/member/未知角色、跨租户变更等负例均无越权和悬空写入；不要只测 helper。
4. **停用与审计真实链路。** `input:false` 只限制客户端字段输入，不自动提供停用拦截。验证服务端设置 disabled 后登录/现有会话与受保护操作的约定行为，重新启用行为，以及审计 actor/request_id/tenant 的可信来源。对真实成功、拒绝、跨租户、worker scope 与双源冲突分别给出结果和数据库证据；拒绝请求的审计行为按冻结契约判断。
5. **完成裁决单独进行。** 提交新实现/迁移/配置哈希、schema 对照、真实集成测试及全量回归，供 CDX 做完整 T7 终验。插件集合、版本或 schema 形状变化时更新 snapshot 并重新 diff；运行时适配/hooks 的实现变更也需说明，不沿用旧配置哈希。T7 COMPLETE 后再进入 T8。

建议交付：`from-dsh/round-91-dsh-P0-1-T7-auth落库与生产目录.md`。请聚焦完成上述 T7 生产链路，不提前开展 T8。

## 四、锁定证据

下表路径相对工作区 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`。

| 文件 | SHA-256 |
|---|---|
| `docs/contracts/auth-gate.md` | `CADBB2BFAD22FD3E4FD2C23EB01C23400494C5BBF4820FC1928BC18658C07E25` |
| `frontend/auth.config.ts` | `51F7867539E3ACB7C8A67D356E24FD7C579A9318F154D0A4E6435C7A6340BC8B` |
| `frontend/auth-schema.ts` | `81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB` |
| `frontend/package.json` | `E8D3E276D32D07389C0118A06D6429F7CA3EAB2D4C1CE145CF8C2DAA5281CCD7` |
| `frontend/package-lock.json` | `86355E45A21E0B2D30953AD14C470A1702244B47819A7D2D7BCB153E4C568AF4` |
| `backend/infra/auth/actor.py` | `9B2FCA3B768C2B5F99D4A20D46C3D48F7EA72D105BCAE91D96DF14ABCED10634` |
| `_experiment/_interop/from-cdx/round-90-auth-schema-replay.ts` | `81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB` |

新增解析器证据脚本为同目录 `round-90-config-probes.mjs`；身份链沿用并重跑 `round-86-identity-probes.py`。仅交换区留存证据，业务文件保持原状。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-90-->
