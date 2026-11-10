# t9-sample-manifest.md — T9 离线样本导入/重放覆盖清单（round-123 R122-3 修正）

> 归属：DSH | 依据：test-strategy.md §六/§八、round-120 R120-2（修正 round-119 错误映射）、
> round-123 R122-3（修正 parse_campaign_metrics→parse_snapshot_row 与 SQLite 吸收表述）
> 状态：P0-1 样本覆盖映射（与代码实际读取一致）；真实微信平台在线采集样本属 P0-3/P0-4 门禁（§14.0 资源未确认）

## 一、样本来源与测试实际读取/断言映射（与 CI 测试实际读取一致）

| 样本文件（实际路径） | 来源 | 实际读取测试 | 断言层级 | 预期 |
|---|---|---|---|---|
| `backend/fixtures/ads/campaign_report_sample.json` | 投放管理列表回读样本（结构化快照） | `test_ads_fixtures.py`（M5 投放样本吸收） | parser（parse_snapshot_row）+ SQLite 吸收 | 字段解析正确、吸收成功 |
| `backend/_management/data-exchange/old-system-assets/fixtures/p2-products.json` | 旧系统 app.db 脱敏提取（产品 17 条） | `test_p2_fixtures.py` | 文件清单 + 字段完整 + 脱敏合规 | count=17、字段集、无外链/密钥 |
| `backend/_management/.../p2-category-memory.json` | 旧系统分类记忆（4 条） | `test_p2_fixtures.py` | 文件清单 | count=4 |
| `backend/_management/.../p2-rule-drafts.json` | 旧系统规则草稿（46 条） | `test_p2_fixtures.py` | 文件清单 | count=46 |
| `backend/_management/.../p2-events-sample.json` | 旧系统事件样本（50 条） | `test_p2_fixtures.py` | 文件清单 + 脱敏合规 | count=50、无外链/密钥 |

> 证明层级说明（round-120 要求明确；round-123 R122-3 修正 parser 名与 SQLite 吸收表述）：
> - **文件清单**：test_p2_fixtures 验证文件存在、count、字段、脱敏（4 文件）；
> - **parser**：test_ads_fixtures 验证 campaign_report_sample 经 parse_snapshot_row 逐行口径解析
>   （元→分 / 枚举中文→英文 / UTC recorded_at；ads/report.py::parse_snapshot_row）；
> - **SQLite fixture-e2e**：test_ads_fixtures 用临时 SQLite ads 模块 + SnapshotCollector.run_once
>   验证样本行吸收为快照行（独立 tmp_path 临时库，不动其他模块库）；
> - **app PG repository**：未接入——ads/campaign 样本具备结构化快照并经 SnapshotCollector 吸收到
>   **临时 SQLite**，但尚无写往 app PG 业务表的 repository 路径（PG 侧入库未接线，为后续真实平台
>   样本接入预留）。

## 二、候选外部样本（round-118/120 列出）

| 文件 | 大小 | 状态 |
|---|---|---|
| `C:/Users/Administrator/Documents/xwechat_files/wxid_d2s1416d9ood22_80b9/msg/file/2026-09/盈亏表T.xlsx` | 51,286,084 B | **已核对元数据存在**；字段适配（Excel 财报表 → 内部模型）与导入演练需用户裁决 |

## 三、样本重放测试接入（T9 CI job4/job6）

```text
python -m pytest backend/tests/test_ads_fixtures.py backend/tests/test_p2_fixtures.py -q
```

（已接入本地 t9_ci_layers.py 与 .github/workflows/ci.yml job4/job6——11 passed 实测。）

## 四、待裁决项

1. 盈亏表T.xlsx 是否纳入离线样本（需字段映射裁决：Excel 财报表 → 内部模型）；
2. 真实平台在线采集样本（P0-3/P0-4 资源未确认 §14.0）——不在 P0-1 范围。

<!--RELAY: 供 CDX round-124 复核 R122-3 修正 -->
