# round-157 DSH：P0-2 聚合入口类型单项回修（R156-1）

> 日期：2026-09-12。输入：`from-cdx/round-156-cdx-P0-2计算门复验与入口单项回修.md`（仅 R156-1）。
> 状态：**C1-b/c 仅入口类型单项回修**；C1-a/事实层/manifest 保持冻结；C2/C3、SKU/M2 实际 DDL、
> manual/workflow、批次 3 继续锁定；M1/M3 范围变更仍待裁决。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、变更文件与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/aggregation.py` | `3B1004CEA7F3B1B216CDD4AD9E16D60D3E52DE0EC72A186DB2038ECF5B92ABDC` | `_validate_event` 增加运行时元素类型检查 |
| `backend/tests/test_report_aggregation.py` | `7396950A98A3D36A76C9B190A485396A5DDF99C38785DB09047FFC477529A7DA` | +3 项（29 项） |

> 未变更：`calculator.py`（`735F67B9...`）、`aggregation_manifest.py`（`5255776E...`）、`selector.py`
> （`FA58F412...`）、`__init__.py`（`5BEDCEE7...`）、`test_report_calculator.py`（`BA5D3900...`）、
> `test_report_aggregation_pg.py`（`2258EF0A...`）、version/repository/collector 事实层——哈希保持 round-155/冻结值。
> **未更换**去重身份、数值口径、作用域策略或 PG 事务策略（round-156 §R156-1 明确无需更换）。

## 二、R156-1 闭合：公开入口元素运行时类型检查

### 2.1 修复位置与内容

`backend/domain/report/aggregation.py::_validate_event`——在**任何字段访问之前**先做运行时元素类型检查：

```python
def _validate_event(e) -> None:
    if not isinstance(e, SourceEvent):
        raise AggregationInputError(f"元素必须是 SourceEvent，got {type(e).__name__}")
    if type(e.tenant_id) is not int or e.tenant_id <= 0:
        raise AggregationInputError("tenant_id 必须为正 int")
    ...  # 字段重验全部保留
```

- `_validate_event` 由公开入口 `aggregate_events`（逐元素调用）与 `SourceEvent.__post_init__` **共用**，
  因此类型门禁对两条路径同时生效；
- 字段重验（正 int 标识 / 非负 int 金额拒绝 bool / 五类 feedback↔subject 配对 / 未知
  aggregation_version 拒绝 / aware 窗口 / 非空 subject_key 与 attribution）**全部保留**；
- 修复前：`_validate_event` 首行即读 `e.tenant_id`，类型注解与构造器校验未封闭公开入口。

### 2.2 两项精确异常证据（CDX round-156 §R156-1 原复现）

在 `backend/` 下用 CDX 原复现代码实测：

```text
DUCK REJECTED (GOOD): AggregationInputError 元素必须是 SourceEvent，got SimpleNamespace
OBJECT REJECTED (GOOD): AggregationInputError 元素必须是 SourceEvent，got object
```

- 字段齐全的 `SimpleNamespace(**asdict(SourceEvent))`：修复前被接受（返回 `1.000000`），
  现在 **`AggregationInputError`**；
- 无字段 `object()`：修复前抛 `AttributeError`，现在 **`AggregationInputError`**（精确类型，非
  AttributeError 子类替代）。

### 2.3 新增测试（`test_report_aggregation.py` +3）

| 测试 | 断言 |
|---|---|
| `test_r1561_duck_namespace_rejected` | 字段齐全 `SimpleNamespace` → `AggregationInputError` |
| `test_r1561_bare_object_rejected_not_attributeerror` | `object()` → `AggregationInputError`（精确，不得为 `AttributeError`） |
| `test_r1561_source_event_still_accepted` | 正例：普通 `SourceEvent` 仍通过（类型门禁不影响合法输入） |

`AggregationInputError` 为 `ValueError` 子类，`pytest.raises(AggregationInputError)` 对
`AttributeError` 会失败，故该断言精确覆盖「不得抛 AttributeError」。

## 三、标准回归

| 项目 | 结果 |
|---|---|
| 十四文件全量回归（185 P0-1 + 85 批次 1 + 31 selector + 39 calculator + 29 aggregation + 7 PG） | **376 passed**，无 pytest warning |
| aggregation 独立 | **29 passed** |
| 计算门独立（calculator 39 + aggregation 29 + aggregation_pg 7） | **75 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | `T9_CI_LAYERS=PASS` |

数据库终态：auth000002 / 31 app 表 / 7 auth 表 / 60 enum / 17 trigger / ad_report_snapshots=0 /
roi_feedback_events=0 / tenants=0 / auth_user=0 / workflow_runs=0 / temp_databases=0。

## 四、保留项与边界

- round-156 已关闭包（R154-1 去重/内容冲突、R154-2 Decimal 上下文、R154-3 字段重验/真实作用域 fixture/
  PG REPEATABLE READ 固定基准与接线、R152-2 三项文档终选）**本轮未改动**，沿用通过。
- 选择器/事实层/manifest 哈希保持冻结。
- C1-b/c 未记 COMPLETE（待 R156-1 复核）；写入门（C2/C3）、SKU/M2 实际 DDL、批次 3 未授权前继续锁定；
  M1/M3 范围变更仍待裁决。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 五、交接

请 Codex 复核 R156-1 单项（`_validate_event` 字段访问前 `isinstance(e, SourceEvent)`、两项精确异常负例、
正例仍通过）并重跑 376 回归。通过后裁决 **C1-b/c COMPLETE**；下一写入门仍需独立授权，非自动开启。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-158-->