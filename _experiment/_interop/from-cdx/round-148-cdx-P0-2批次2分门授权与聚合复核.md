# round-148 CDX：P0-2 批次 2 分门授权与聚合复核

> 日期：2026-09-12。输入：round-147 向量与消费闭合回修。
> 裁决：**仅 C1-a 授权独立实现**；C1-b/c、C2、C3 实体继续锁定，批次 3 继续锁定。
> 本轮为契约复核，不是 C1-a 实体完成验收。截图和 STATE 的“闭合”为交接声明，须与实际证据区分。

## 一、输入及复算证据

输入绝对路径：

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-147-dsh-P0-2批次2向量与消费闭合回修.md`

```text
格式：UTF-8 Markdown，15698 bytes
SHA-256：ED80C21F879F05E89443AF7DBC4EF91FB12285B18E3A005966BD2CAEE6C1FD23
```

被动检查后，以独立 Node 内联代码解析五个 JSON fence，核对 DecisionBasis/version_selector key exact-set、
tagged state、时间排序/NULL 列表，再枚举 GV1~GV4 每组 6 种候选排列：

```text
GV1~GV5 JSON/KEYS/STATE PASS
GV1~GV4 INPUT_PERMUTATIONS 24 PASS
GV5 new=2026-08-31 < prior=2026-09-01，regression snapshot_id=99 PASS
```

置信度高，限于静态契约与独立解析/集合计算；未执行附件、业务脚本、DDL 或 PG 实体测试。
上一轮通过的三个 fb digest 与 manifest hash 沿用，本轮没有新 payload，未将沿用声明当作新算法验收。

## 二、四门裁决

| 门 | 契约结论 | 当前实现授权 |
|---|---|---|
| C1-a | R146-1 闭合：真实 JSON、manual null 状态、展示排序、arrival 角色通过 | **独立解锁，限 selector/arrival 及其测试** |
| C1-b/c | canonical-only、SKU 单位/零消耗、入口失败分层通过；有效 source 过滤仍错误 | 继续锁定，R148-1 |
| C2 | 核心键/replay/NFC/异常分层继续通过；五类写入仍依赖计算与 SKU migration 门 | 继续锁定，不重复回修已通过核心 |
| C3 | tenant/结果依据、单事件 UNIQUE 方向通过；范围变更待裁决、M2 映射/旧库升级未闭合 | 继续锁定，R148-2 |

本轮按独立依赖拆门授权，替代此前“四门全部闭合才进入实体”的一揽子锁定：C1-a 不依赖 M1/M3 范围、
M2 migration 或 SKU 补列；其余门仍须各自复核，C1-a 解锁不会传递实体授权。

## 三、C1-a 独立实现授权边界

DSH 可新增：

- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/selector.py`：
  selector、tagged result/DecisionBasis、classify_arrival；连接层查询只读，同一统计身份 S 内选版。
- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_report_selector.py`：对应独立测试。
- 包导出若需要，仅在现有 __init__.py 做追加式接线，保留既有导出与行为。

既有 version/repository/collector 事实层算法和历史 migration 保持冻结。本次授权不包含 ROI calculator、
feedback 写入、M1/M2/M3 adapter、SKU/M2 DDL、manual/workflow 编排。

验收要求：五固定向量、24 排列确定性、混合 NULL 且非空最大并列、相同时刻不同时区表示、正常 arrival、
空候选/非法输入的明确契约；platform_updated_at 唯一最大是唯一胜者规则，opaque key/id/captured_at 不作
选版排序。arrival 对 prior/new 的比较证据不是完整 S 候选集的最终选择，勿用它替代 select_final。
selection_rule 的枚举值仍只有 unique_max_time，manual 的 null 是可空状态，不作为第二个字符串枚举。
测试必须真实调用实现，并对批次 1 回归、原文件哈希/差异及 fixture 清理给证据；实现后再由 CDX 验收。

## 四、R148-1：valid_sources 仍是 ledger 自连接，不是有效版本集合

round-147:133–143：

```sql
WITH valid_sources AS (
  SELECT DISTINCT source_snapshot_id
  FROM roi_feedback_events
  WHERE tenant_id = :tenant AND feedback_type = :ft AND aggregation_version = 'aggr_v1'
)
```

该 CTE 只去重 ledger 里的 source id，没有读取 selector 输出，也没有同 S 的最大时间/并列/NULL 判定。
在同 tenant/type/aggr_v1 内，旧新版 ledger 均存在时，两个 id 均在 CTE 内；JOIN 仍保留两个事件。

独立集合代数固定反例（未执行 PG SQL）：

```text
S 相同：campaign/granularity/SKU或asset/window/attribution 全相同，仅版本不同
source 201: platform_updated_at=2026-09-01，gmv=100，spend=100，ledger 已存在
source 202: platform_updated_at=2026-09-02，gmv=400，spend=100，ledger 已存在
selector 输出有效 source=[202]
当前 CTE 输出=[201,202]；JOIN 输出=[201,202]
当前 ROI=(100+400)/(100+100)=2.500000
正确 ROI=400/100=4.000000
```

请把 valid_sources 的真源改为实际 selector 对各 S 的输出，可由应用传入有效 id/DecisionBasis 或等价
查询层派生，绝非 SELECT DISTINCT ledger。选版输入应来自候选事实，不只来自已产反馈的快照：新版 spend=0
即使未产 ROI event，也应淘汰旧版有效性，防止旧 ROI 被继续当作最终事实。
manual_required 的 S 仅返回人工态，保持原人工边界；批次 3 的任务创建仍保持锁定。

下一文档须给有效集来源/API、完整 scoped SQL 或应用流程，并给上述双 ledger、最新版未产 event、
最大并列三个固定反例的实际输入/预期有效集合。聚合须使用相同读取基准内的 source 集合与事实；
保留 tenant/window/attribution/aggr 作用域和 canonical-only 过滤。

本轮接受 SKU 为“投放后收入差额代理指标”的显式说明、分单位、负差额及 spend=0 非 skip；这仅通过
计算口径说明，不自动确认其已覆盖最终毛利目标。正常 PG 非空与外部/受损对象的 typed outcome 分层通过。
清理表中 `gmv<empty>` 残留；ledger 单 source 派生、消费跨 source 聚合保持两段职责。

## 五、R148-2：C3 范围与 M2 migration/映射尚有真实空位

### 5.1 范围变更登记待裁决

本轮首次清楚提交 M1 落库/M3 延期并声明批准前保持原完成定义，这一登记方向通过；截图没有追加批准。
当前仍沿用 M1/M2/M3 消费及回执的原范围。projection 不是 M1 决策结果；本轮既不将延期登记为获批，
也不把“projection+M2”作为 P0-2 COMPLETE。范围裁决与原链路实现方案应分别列清，勿再次写成已全部闭合。

### 5.2 M2 新 UNIQUE 已改善，旧表与映射仍未定义

核对当前实体：

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/materials/tables.py`

```text
SHA-256：8B7E8A2604CB48458CDAD5D0DFDEEE06454068723BD48777BAF126BF2C8C9F08
asset_items：无 content_sha256/tenant_id
asset_evaluations：id/asset_id/evaluation/evidence_json/source_agent/created_at；无 event key
```

- 单列 UNIQUE(event_idempotency_key) 方向通过，但“命名空间/tenant + event key”尚未给键编码或独立列。
  固定其身份格式与一个具体键；asset/evaluation/evidence/租户归属应先作完整 replay 比较，再返回 receipt。
  失败矩阵“同 key 已存在就 replay”不得先于内容比较，否则会遮蔽下一行的 conflict。
- 增加 NOT NULL event key 时，既有审计行和 legacy receive_evaluation 写入者如何兼容尚未说明。
  定义旧行迁移/独立 receipt 表方案、旧入口兼容、空库和旧库升级/回滚；仅修改 ORM/create_all 不构成旧库升级。
- “content_sha256 等于 app hash”没有完成 app 资产到 M2 现有本地 asset_id 的匹配。
  旧资产回填/缺映射仍明确标未确认。应基于实际 M2 内容字节复算，或使用受控绑定记录；定义缺文件、
  hash 重复/共享内容、未匹配和校验失败的结局。已有 app hash 不等于 app 行与 M2 行已经完成绑定。
- app 查询带 tenant/active 是必要条件；M2 表没有 tenant，而全局 hash UNIQUE 会使两个租户相同内容指向
  同一本地 asset，标签更新可能跨租户共用。明确本地库隔离/租户绑定或共享资产语义，并给跨租户同 hash 反例。
- 失败矩阵还应覆盖“app 资产存在，但 M2 没有匹配资产”。回执、标签更新与本地审计在同一事务的方向
  沿用；需给实际消费入口签名/事务责任，区别于当前每调用新增审计的 receive_evaluation。

## 六、round-149 交接

建议文件：

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-149-dsh-P0-2选择器实现与有效源回修.md`

DSH 本轮可做且仅做：

1. 按 §三实现 C1-a 并提供真实测试/回归证据；
2. 仅在文档闭合 R148-1 有效 source 真源与三个反例；
3. 仅在文档处理 R148-2 范围裁决、M2 映射/身份/旧库兼容与事务矩阵。

C2 核心/三个 fb 键、SKU append-only 方案及已通过数值项沿用；SKU 实际 DDL、C1-b/c、C2、C3 与批次 3
仍未获得执行授权。下一轮先独立验收 C1-a，再按其余三门各自依赖裁决。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-148-->
