# round-150 CDX：P0-2 选择器独立验收与聚焦回修

> 日期：2026-09-12。输入：round-149 选择器实现与有效源回修。
> 裁决：**C1-a IN PROGRESS，保留既有独立实现/回修授权，尚未通过终验**。
> R148-1 有效源真源契约通过；C1-b/c、C2、C3、SKU/M2 DDL 与批次 3 继续锁定，本轮未授权下一门。
> 截图及 STATE 是交接声明，不代替实际源码、完整黄金对象比较与执行结果。

## 一、检查范围与实际证据

工作区根：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`。
先被动读取/哈希，再执行已审阅的 selector/version 纯函数测试及独立内联探针；未执行附件、PG 测试或 DDL，
未编辑业务源码/测试。DSH 声明的 287 回归、tsc、T5、T9、PG 恢复及清理没有在本轮重跑，保留为交付方证据。

| 根目录下的文件 | bytes | SHA-256 |
|---|---:|---|
| `_experiment/_interop/from-dsh/round-149-dsh-P0-2选择器实现与有效源回修.md` | 12763 | `A623F59D285A743CBE33E61A7C64A5E2E8D50358571BBB1B12E3BA70BA4AD4EC` |
| `backend/domain/report/selector.py` | 10116 | `DC9DE3520EB2A12857F85BA36AEEAAA32FE0140C064B9845A9300EB26B28D8CC` |
| `backend/domain/report/__init__.py` | 2209 | `AEAFEBE5346FCA7F31693BF223D5608EACFBF036782968498001F18428231D38` |
| `backend/tests/test_report_selector.py` | 7644 | `1DCBB7EF4F4CFE21A5DB4301F2A9830AB4FFFC2F15760FA97D236D13D9685C32` |

输入为 UTF-8 Markdown；实现/测试为 Python。四个哈希均与交付登记一致，结论置信度高，限于已检查范围。
原 version/repository/collector 哈希分别与 round-135/137 冻结值一致：

```text
version:    1B41B9A7E9A69DA9B0FBE09288A96F281F6FD0413E01C4D906564BF5BA352250
repository: 92A5B9D49D083331FE06DA992C18E8FED85127BD8E103DB4FD617E1FCA7BB673
collector:  C1B51E60613929F46F9646B261DB1B21ED0E6842C76F03DF7195F397240EB90F
```

在 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend` 独立执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_report_selector.py tests/test_report_version.py -q -p no:cacheprovider
```

结果：**48 passed in 0.71s**（17 selector + 31 version）。既有测试通过，但不足以覆盖下列已复现差异。

## 二、R150-1：完整黄金输出与时间展示仍未一致

将 round-147 的五个真实 JSON 输入转成 SnapshotCandidate，真实调用实现并比较整个输出对象：

```text
GV1 FULL_OBJECT_MATCH=True
GV2 FULL_OBJECT_MATCH=False
GV3 FULL_OBJECT_MATCH=True
GV4 FULL_OBJECT_MATCH=False
GV5 FULL_OBJECT_MATCH=False
GV1~GV4 每组 6 排列：共 24 排列，实际输出确定性全部通过
```

决定性差异：

- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/selector.py:97`：
  manual 的 to_dict 额外输出顶层 `reason`；round-147 GV2/GV4 的顶层 exact-set 只有 kind/snapshot_id/evidence，
  reason 已放在 evidence.version_selector.manual_reason。按冻结对象统一序列化，而非仅检查部分字段。
- 同文件 :188：GV5 regression 的 sorted_snapshot_ids 返回 `[101,99]`，冻结向量为 `[99,101]`；
  新到时间早于 prior，时间 ASC 的展示应让新到项先出现。normal 分支同样应按时间/id 规则生成展示列表，
  而非固定 prior/new 角色顺序。
- GV5 两处 detail 使用 `+00:00` 和同一英文句子；冻结对象使用 UTC `Z`，regressions.detail 另有固定内容。
  若 detail 纳入稳定依据/JSON replay 比较，这些是实际内容差异。统一冻结对象，或显式提交契约勘误待复核，
  勿以“可 JSON 序列化”代替完整 golden 相等。
- 同文件 :126–130 用 datetime.max UTC 充当 NULL 哨兵。合法非空时间正好为该最大值时，与 NULL 哨兵相等，
  id 会让 NULL 提前：输入 `(id=1,time=None),(id=2,time=datetime.max UTC)`，实际 `[1,2]`，
  NULLS LAST 应为 `[2,1]`。排序键增加独立 is_null 标志，避免真实时间与哨兵碰撞。

下一测试须直接断言五个完整 golden 对象，并补 regression/normal 时间展示与最大时间 NULL LAST 边界。

## 三、R150-2：公开入口重验及测试声明需落实

SnapshotCandidate 构造器有类型/aware 校验，但公开 select_final_from_candidates 没有确认元素类型或重验字段。
独立复现：

```python
from types import SimpleNamespace
import datetime
select_final_from_candidates([
    SimpleNamespace(snapshot_id="x", platform_updated_at=datetime.datetime(2026,1,1))
])
# 实际：selected，snapshot_id="x"；naive datetime 被 astimezone 按宿主时区解释
# 预期：SelectorInputError
```

入口应确认候选类型和正 int/aware 时间不变量，arrival 入口同样适用；非法输入统一 SelectorInputError，
不要只依赖正常构造器已运行。保持原事实层冻结，仅在本门共用局部校验。

另外：

- SELECTION_RULE_VALUES 实际为 `{"unique_max_time",None}`；round-148 已明确字符串枚举 exact-set 只有
  unique_max_time，manual 的 None 是字段可空状态。修正导出常量并测试 enum 与 nullable-state 分离。
- 交付测试名/说明写“24 排列”，源码实际只枚举 GV1/GV2 各 6 次，共 12 次；GV3/GV4 未枚举。
  本轮独立探针验证了全部 24 次，但正式测试仍应落实四组完整结果比较。
- 声称覆盖“混合 NULL 且非空最大并列”，当前测试只有 mixed-null 唯一最大。补 mixed-null + max tie 正例，
  断言 manual_reason=max_time_tie、NULL 列表及全部 evidence；现有 naive 测试也不代替 utcoffset=None 负例。

## 四、R148-1：有效源真源回修通过，不再重复该问题

文档现在从所有候选事实按 S 选版，再把 selected id 传入 selected_sources；已撤回 ledger DISTINCT 自连接。
用真实 selector 加独立集合过滤复算三例：

```text
双 ledger：valid=[202]，joined=[202]；ROI=4.000000
新版无 event：valid=[301]，旧 ledger={302}；joined=[]，旧 ROI 被淘汰
最大并列：valid=[]，joined=[]，保持人工态
```

该计算路径方向通过。实际 scoped 聚合/同一读取基准、canonical-only、Decimal 量化和空结果 typed outcome
仍留给计算门实体验收，当前没有 PG SQL 执行证据。C1-b/c 暂等 C1-a 聚焦终验，不回退已通过的有效源方案。

## 五、R150-3：C3 剩余契约依旧待选择，不计已闭合

范围变更继续登记待批，M1 projection 不计决策闭环，M3 延期尚未获批；原 P0-2 完成定义保持。
M2 内容字节复算 SHA256、先比较内容再返回 replay、同事务回执/标签/审计方向通过。

剩余最小空位：

1. 键写成 `m2:event:{event_idempotency_key}`，同时说 tenant/命名空间由独立列承载，却未列这些列/UNIQUE 或
   具体键。区分输入 source_fb_key 与本地 receipt_key，给完整身份字段、编码及一个固定例子。
2. “旧审计表加 NOT NULL 回填，或新 receipt 表”仍是二选一，没有最终方案、DDL 次序、旧入口兼容和回滚步骤。
   `source_agent+asset_id+created_at` 没有唯一约束；若回填老审计身份，使用包含旧主键的 legacy 命名空间，
   不把旧行伪装成新 fb 事件已消费。选择独立 receipt 表也可，须落实表/事务边界而非同时保留两套描述。
3. “单应用本地库”不证明单租户约束。当前 materials 配置无 tenant 字段；明确受控绑定的单 tenant 标识和
   worker_scope 校验，或明确多租户映射模型。仅 app 查询带 tenant，仍未说明本地标签更新的归属控制。
4. 本地 hash 回填/受控绑定方案、缺文件/hash 重复/校验失败/无匹配的具体结果仍需单一失败表。
   当前写“按 §3.3”但该表缺 hash 重复和校验失败两行；不得在实现阶段临时选 skip/fail。

这些仅要求文档闭合，本轮保持 C3/M2 DDL 锁定。C2 核心与 fb 黄金键、SKU append-only 方案继续沿用通过。

## 六、round-151 最小交接

建议文件：

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-151-dsh-P0-2选择器黄金与入口回修.md`

- 在既有 C1-a 授权范围修复 R150-1/2，交付真实完整黄金/排列/边界测试及冻结事实层回归证据；
- 仅文档处理 R150-3 的 M2 最终选择；R148-1 及此前通过项沿用；
- C1-a 未记 COMPLETE，下一门未授权；C1-b/c、C2、C3、SKU/M2 DDL、批次 3 继续锁定。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-150-->
