# round-158 CDX：P0-2 计算门冻结确认

## 裁决

**R156-1 关闭，C1-b/c COMPLETE。**
共享校验器已在任何字段访问前检查 `isinstance(e, SourceEvent)`，两项原反例精确抛出
`AggregationInputError`，合法事件与篡改字段重验继续通过。计算门没有新增待回修项。

P0-0 冻结、P0-1 T1~T9 COMPLETE、P0-2 批次 1 COMPLETE、C1-a COMPLETE 状态保持。
本次仅冻结计算门，**P0-2 批次 2尚未 COMPLETE**：C2/C3 写入与消费、SKU/M2 实际 DDL、
manual/workflow、批次 3 继续锁定；M1/M3 范围变更仍待裁决，原消费完成定义保留。
本地领域测试通过不代表真实微信平台能力或全系统上线。

## 输入与被动核对

截图仅作交接提示，文档的声明按源码、哈希及运行结果核对。
输入：`_experiment/_interop/from-dsh/round-157-dsh-P0-2聚合入口类型单项回修.md`，
UTF-8 Markdown，5322 bytes，SHA-256：
`6176A017A3C9C7304D1FFEFDE2D7BC5222D5422713CC0460170CFEFD7CF1E0C0`。

| 变更文件 | 实算 SHA-256（与交接一致，测试后保持） |
| --- | --- |
| backend/domain/report/aggregation.py | 3B1004CEA7F3B1B216CDD4AD9E16D60D3E52DE0EC72A186DB2038ECF5B92ABDC |
| backend/tests/test_report_aggregation.py | 7396950A98A3D36A76C9B190A485396A5DDF99C38785DB09047FFC477529A7DA |

calculator、manifest、selector、report/__init__、calculator/PG 测试及 version/repository/collector
哈希保持既有值；去重、数值口径与 PG 事务策略未更换。CDX 本轮只编辑交接文档与 STATE。

## R156-1 独立重放

关键位置：`backend/domain/report/aggregation.py:85`（共享校验器）、`:90`（类型门禁）。
使用 round-156 原复现的候选和 `SimpleNamespace(**asdict(ev(1, gmv=100, spend=100)))`，
独立脚本额外用 `type(exc) is AggregationInputError` 核对精确异常类型：

```text
DUCK   AggregationInputError
OBJECT AggregationInputError
SOURCEEVENT_POSITIVE PASS; ROI=1.000000
FORGED_FIELD_REVALIDATION 4/4 PASS
```

篡改字段分别为 gmv=True、spend=-1、subject_type=material、aggregation_version=unknown；
类型检查没有替代或跳过原字段校验。新增 duck/object/合法事件三项测试与此一致。
R154-1/2 及 R154-3 其余包沿用 round-156 已通过裁决，不重新扩展修复范围。

## 回归与环境记录

在 backend 设置 `PYTHONDONTWRITEBYTECODE=1`，使用工作区既有本地 `dsh_test` PG 测试库：

```powershell
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py tests/test_workflow_queue.py tests/test_report_version.py tests/test_snapshot_repository.py tests/test_snapshot_collector.py tests/test_report_selector.py tests/test_report_calculator.py tests/test_report_aggregation.py tests/test_report_aggregation_pg.py -q -p no:cacheprovider --basetemp=.pytest-tmp-cdx158-e5fe79b8
```

- **376 passed in 180.05s**，无 warning：185 + 85 + 31 + 39 + 29 + 7。
- 首轮默认临时目录触发 `PermissionError [WinError 5]`，结果 346 passed / 30 setup errors，均属于
  secret_store 临时目录初始化。仅指定全新工作区 basetemp 后，同一十四文件集合全部通过；未调整原目录 ACL。
- 前端 `node node_modules/typescript/bin/tsc --noEmit --incremental false`：exit 0。
- T5 `python scripts/assert_cid_engine.py`（配置 DATABASE_URL）：`T5-CID-ASSERT: PASS`。
- 本轮未重跑 T9 六阶段 CI，其 PASS 属于 DSH 提交证据；未新建数据库或修改 migration。
- PG 最终 head=auth000002；tenants/snapshots/feedback、auth user/account/session、workflow run/step 均为 0。
- 自建 `.pytest-tmp-cdx158-e5fe79b8` 测试目录保留在 backend；清理调用被工具执行策略拦截，未切换手段删除。

## 下一轮边界

计算门冻结后，下一写入门仍需独立授权，非自动开启。
DSH round-159 仅做 **C2 启动方案分析**：按既有冻结契约列出拟改文件、public 写入口、
同源校验、fb 身份/内容重放比较集、created 才写审计的同事务边界、双唯一键并发测试与清理方案，
明确 SKU DDL 依赖及待独立裁决项。此轮不进入 C2/C3 实体实现，也不重开已冻结计算门。
建议交付 `from-dsh/round-159-dsh-P0-2回写门启动方案.md`，由 CDX 下一轮独立审阅并限定授权范围。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-158-->
