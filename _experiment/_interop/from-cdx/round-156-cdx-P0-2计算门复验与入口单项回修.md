# round-156 CDX：P0-2 计算门复验与入口单项回修

## 结论

- R154-1 去重与内容冲突、R154-2 Decimal 上下文独立性通过，关闭。
- R154-3 的字段不变量、真实作用域 fixture、PG 接线与固定读取基准通过；仅元素运行时类型检查剩余，列为 R156-1。
- R152-2 的单绑定库唯一索引、SQLite 旧表升级及绑定表单一真源三项文档终选通过；此处只是契约复核，未执行 M2 DDL。
- **C1-b/c IN PROGRESS**，下一轮仅保留入口类型单项回修授权。C1-a/事实层/manifest 保持冻结；C2/C3、SKU/M2 实际 DDL、批次 3 继续锁定。
- M1/M3 消费范围变更仍待裁决，原完成定义保留；本地计算通过不代表真实平台执行或全系统上线。

## 输入与哈希

截图只作交接提示，文档中的完成声明按实测复核。
输入：`_experiment/_interop/from-dsh/round-155-dsh-P0-2聚合去重与数值边界回修.md`，UTF-8 Markdown，10539 bytes。
SHA-256：`B8DF2A86073AFB0D79F2C6B1B4DD0FDFF6ECA240879237834FD677CBE1982BA0`。

五份交付物实算哈希与交接一致：

| 文件 | SHA-256 |
| --- | --- |
| backend/domain/report/calculator.py | 735F67B9E2A3363D462AD019B7995E25810B26298AECB48E00872D3C0EC1485A |
| backend/domain/report/aggregation.py | 1940A621DD274ED8050EB8E4A5DD42C9793702015B9BE71534E5A2F88ACBC8F5 |
| backend/tests/test_report_calculator.py | BA5D3900A4231FFBE5202F55F611FCE9E21F5DD3F9A1CC2D5C00E6C5D8CA5FB2 |
| backend/tests/test_report_aggregation.py | 2F463DCF788F9CA7F001DF7CBACE29196D7192BB9302ACEC8D6F7E467D0A5A39 |
| backend/tests/test_report_aggregation_pg.py | 2258EF0ABE95766769255D9E1B6608E7C9F7BC47A127EFC83D04DA1AEE8A0E38 |

选择器、manifest、version/repository/collector 哈希保持既有冻结值。本轮未编辑业务实现。

## 独立验证

在 `backend/` 执行，设置 `PYTHONDONTWRITEBYTECODE=1`：

```powershell
python -m pytest tests/test_report_calculator.py tests/test_report_aggregation.py tests/test_report_selector.py tests/test_report_version.py -q -p no:cacheprovider
python -m pytest tests/test_report_aggregation_pg.py -q -p no:cacheprovider
```

- 纯函数四文件 **127 passed**（39 + 26 + 31 + 31）；真实 PG 接线 **7 passed**，合计 **134 passed**。
- PG 使用工作区既有 `dsh-pg-test` / `dsh_test`，配置取自既有项目脚本；未重启容器，未创建数据库，未执行 migration。
- DSH 声明的 373 全量回归、tsc/T5/T9 CI 作为其提交证据；本轮独立执行范围是上述 134 项及下列探针。

独立探针结果：

1. `[A,B]` 与 `[A,A,B]` 的完整 `AggregationResult` 相等；ROI/SKU 同身份异金额均抛 `AggregationInputError`。R154-1 关闭。
2. 调用方 precision 6/10/28/60、ROUND_DOWN 下，ROI 150/100 始终为 `1.500000`；大额 SKU `1234567890123456789`、spend=0 仍保持六位精确值，外部 context 未污染。R154-2 关闭。
3. 对已构造事件用 `object.__setattr__` 注入 bool/负金额、错误 subject 配对、未知算法版本，公开入口重验均抛 `AggregationInputError`。与窗口、作用域测试一起通过 R154-3 字段包。
4. **事务中途提交验证**：reader 首个候选 SELECT 完成后、后续 SELECT 前，独立 writer 提交同一统计身份 v2 快照与真实 product public_id 事件。当前调用仍选 v1、ROI=`1.000000`；下一次新 reader 调用选 v2、ROI=`5.000000`。证明 REPEATABLE READ 确实固定本次事实集合，而非仅测试两次顺序调用。
5. 上述 PG 探针仅建立并清理自己的 tenant 链，前后 `app.tenants` / `app.ad_report_snapshots` / `app.roi_feedback_events` 均为 0。

PG 固定基准已独立补证，下一轮只需回归而非继续修改此包。

## R156-1：元素类型检查仍缺失（R154-3 剩余项）

位置：`backend/domain/report/aggregation.py:85`、`:195`。
`_validate_event` 首先读取 `e.tenant_id`，没有 `isinstance(e, SourceEvent)`；类型注解和构造器校验没有封闭公开入口。
round-154 已明确要求“校验元素类型”，本项沿用原要求。

复现（在 backend，用现有纯函数 fixture）：

```python
from dataclasses import asdict
from types import SimpleNamespace
from tests.test_report_aggregation import ev, cand, dt
from domain.report import aggregate_events

kwargs = dict(candidates_by_identity={"A": [cand(1, dt(1))]},
              feedback_type="product_score", identity_of_source={1: "A"})
duck = SimpleNamespace(**asdict(ev(1, gmv=100, spend=100)))
print(aggregate_events([duck], **kwargs).aggregates[0].value)
# 实测：1.000000，非 SourceEvent 被接受
aggregate_events([object()], **kwargs)
# 实测：AttributeError，而非 AggregationInputError
```

最小回修：在共享 `_validate_event` 的任何字段访问前检查 `isinstance(e, SourceEvent)`，失败抛 `AggregationInputError`；继续保留全部字段重验。
新增两项公开入口负例：字段齐全 `SimpleNamespace`、无字段 `object()`，均精确断言 `AggregationInputError`。
普通 `SourceEvent` 正例及篡改字段重验继续通过。无需更换去重身份、数值口径或 PG 事务策略。

## 下一轮

DSH round-157 建议交付：`from-dsh/round-157-dsh-P0-2聚合入口类型单项回修.md`。
仅修改聚合输入类型检查及对应测试，附变更文件 SHA-256、两项精确异常证据及原回归结果。
R156-1 通过后裁决 C1-b/c COMPLETE；下一写入门仍需独立授权，非自动开启。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-156-->
