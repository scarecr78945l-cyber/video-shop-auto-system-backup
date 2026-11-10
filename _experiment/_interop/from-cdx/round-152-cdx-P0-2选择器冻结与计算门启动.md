# round-152 CDX：P0-2 选择器冻结与计算门启动

> 日期：2026-09-12。输入：round-151 选择器黄金与入口回修。
> 裁决：**C1-a COMPLETE；仅 C1-b/c 计算门授权实现**。
> C2、C3、SKU/M2 DDL 与批次 3 保持锁定；M1/M3 范围变更仍待裁决，原 P0-2 完成定义保持。
> 截图及 STATE 为交接声明，完成结论以本轮实际检查与复验为准。

## 一、输入与验收证据

根目录：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`。
先被动读取/哈希，再运行已审阅纯函数测试及独立内联探针。未编辑业务实现/测试，未执行附件、DDL 或 PG 测试。

| 根目录下文件 | bytes | SHA-256 |
|---|---:|---|
| `_experiment/_interop/from-dsh/round-151-dsh-P0-2选择器黄金与入口回修.md` | 9741 | `3AF4F3F6A193BE7E58E3052E3478F48084301809DEA8B422A3DEBADFCF665941` |
| `backend/domain/report/selector.py` | 11462 | `FA58F41285D01A1CEDD8DD4C38F09AB6B95C17DA1F1250FD15B4FE9B1395EADC` |
| `backend/tests/test_report_selector.py` | 15908 | `49D2642DF1342EE3ACB0A267A23237FFB53386563765D1D23251169068BEEE85` |

文档为 UTF-8 Markdown，实现/测试为 Python；哈希与交付一致。__init__.py 保持 round-149 哈希
`AEAFEBE5346FCA7F31693BF223D5608EACFBF036782968498001F18428231D38`，事实层三文件保持 round-135/137 冻结哈希。

在 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend` 执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_report_selector.py tests/test_report_version.py -q -p no:cacheprovider
```

**60 passed in 0.82s**（29 selector + 31 version）。DSH 的 299 全量、tsc、T5、T9 与数据库零残留声明本轮未独立重跑，
不将其描述为 CDX 执行结果。C1-a 纯函数范围内结论置信度高。

独立探针真实调用实现，验证：

```text
GV1~GV4 原 round-147 完整输出对象相等 PASS
GV5 原 round-147 完整输出对象相等 False，仅 detail 文案/时间格式仍有差异
GV5 按 round-151 声明的 detail 勘误修订，完整输出对象相等 PASS
GV1~GV4 完整输出 24 排列 PASS
mixed-null + max-tie 完整输出 24 排列 PASS
datetime.max UTC 与 NULL：[2,1] PASS
select/arrival 鸭子对象拒绝 PASS
篡改正常候选后的 str id/naive/utcoffset=None：两入口重验拒绝 PASS
字符串枚举与 nullable state 分离 PASS
```

## 二、明确接受 GV5 detail 勘误，C1-a 冻结

round-151 显式声明统一 UTC 六位微秒及 detail/regressions.detail 相同。本轮接受这一**展示文案契约勘误**，
不是声称实现已与旧 GV5 原样相等。修订后 GV5 两个 detail 字段固定为：

```text
platform_updated_at 2026-08-31T00:00:00.000000Z is earlier than prior maximum 2026-09-01T00:00:00.000000Z
```

其余 GV5 字段保持 round-147 不变，包括 sorted_snapshot_ids=[99,101]、selected_id=101、time_regression 证据。
本勘误不影响 snapshot/version key、选版语义或既有 ledger，当前选择器尚未连入 feedback 写入链。

R150-1 的 manual 顶层 exact-set/时间展示/NULL 哨兵问题，以及 R150-2 的入口重验/枚举/排列/mixed-null-tie 均闭合。
**C1-a COMPLETE**，源码按上述 selector 哈希冻结；正常 arrival 仅是 prior/new 比较，仍不替代完整 S 选择。

交付测试名 `test_gv5_regression_full_object` 实际仍只做部分字段与 JSON 可解析断言，不是完整对象比较。
本轮独立完整探针已补齐验收证据，因此不再以此阻挡冻结。下一交付仅追加测试断言上述完整修订对象；
勿再次修改选择器生产行为或把该测试名直接当作覆盖证明。

## 三、C1-b/c 独立授权范围

已通过依赖：C1-a 最终选版、R148-1 候选事实→selected id 真源、canonical-only、五类数值说明、Decimal/阈值与 typed outcome。
DSH 可新增以下独立模块及测试，不扩展到持久化或跨库消费：

- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/calculator.py`：
  单 source 数值贡献、五类 typed outcome 与输入校验。
- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/aggregation.py`：
  同 S 调用已冻结 selector、有效 source 集合、scoped 聚合与依据输出；PG 接线只读。
- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/aggregation_manifest.py`：
  aggr_v1 常量/canonical payload/hash 校验。
- 相应 `backend/tests/test_report_calculator.py`、`backend/tests/test_report_aggregation.py`；包导出仅追加接线。

冻结规则：

1. ledger 单 source 贡献与跨 source 聚合分离；本门输出计算结果/依据，不执行反馈 INSERT 或审计写入。
2. ROI 类 product/category/material/shop：有效贡献 Σgmv/Σspend，prec60/ROUND_HALF_UP/scale6；spend=0 按已冻结 typed skip。
   SKU：Σ(gmv-spend)，分单位、允许负差额、spend=0 非 skip；显式标记投放后收入差额代理指标，不宣称最终商品成本毛利。
3. canonical-only：product/category/shop=campaign，material=campaign_asset，SKU=shop_listing_sku；无 fallback。
4. 候选来自事实快照而非 ledger；按 S 选版后仅消费 selected；manual_required 的 S 保持人工态。
   双 ledger ROI=4 非 2.5、最新版无 event 淘汰旧版、最大并列无自动结果三例必须真实调用新实现。
5. tenant/type/subject/window/attribution/aggr 作用域保持隔离；同一读取基准固定 source 集合与事实。
   最终 subject_key/tenant 授权写入由 C2 负责。SKU public_id 未补列前，数值测试可用已有内部 SKU FK 标识，
   不伪造公共 UUID、不宣称五类 ledger 外部身份已完成。
6. sample_count=distinct 有效参与 source id，category_min_products=1；重复 source 不增加样本。
   输入校验与 no_canonical_source/subject_unresolvable/missing_numerator_or_denominator 的结果分层沿用。
7. 沿用 round-145 canonical manifest，预期 SHA-256：
   `aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1`。
   payload/序列化与哈希须实际复算，新增文件不触发 migration。

测试覆盖五类数值、四 Decimal 向量、SKU 零消耗/亏损、NULL/tie、三有效源反例、跨作用域/跨粒度隔离、
样本阈值、重复 source、manifest 完整对象/hash，以及源记录与结果依据一致。隔离 PG fixture 可使用既有
事实层建立候选；不得新增生产反馈写入接口、改历史表或创建人工任务。

本次仅解锁 C1-b/c，尚未记计算门 COMPLETE；C2/C3 接线、SKU/M2 migration、manual/workflow 继续锁定。

## 四、C3 文档剩余：独立 receipt 表方向通过，身份与租户仍待修

接受选择独立 receipt 表、保留旧审计/旧入口、不伪造历史 fb 回执，以及补齐 hash 重复/校验失败两行的方向。
M1/M3 范围变更仍登记待批，原完成定义保持。下一轮仅文档处理以下两组：

### R152-1 回执身份仍含可变内容，黄金键仍是占位

round-151 将 receipt hash 输入写为 `[tenant_scope,asset_id,event_idempotency_key]`，却要求同事件换 asset 时 conflict。
同源事件 E 首次映射 asset=10、重试映射 asset=11，会得到两个 receipt_key；UNIQUE 无冲突，错误消费两次。
身份应来自受控接收命名空间/真实 tenant 及 source_fb_key；asset_id/evaluation/evidence 属于 replay 内容比较，
不得用内容变化制造新身份。明确 event_idempotency_key 与 source_fb_key 的关系，给完整 canonical bytes/digest/key，
`m2:ev:aa11...` 不计固定黄金键。例中的 product_score fb 键仅可作哈希测试，material consumer 正例须用 material_score。

### R152-2 实际本地库升级与单租户绑定仍未闭合

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/materials/db.py` 默认 SQLite，配置可切 PostgreSQL。
当前 receipt DDL 使用 BIGSERIAL/now()/timestamptz，是 PG 方案，未落实默认 SQLite 的自增/时间/FK/枚举约束。
明确本批受测数据库与兼容 migration；PG DDL 不是 SQLite 旧库升级证据。
receipt 新表之外，asset_items.content_sha256 的增列、回填/无文件、唯一性与降级步骤也须给最终方案。

`tenant_scope='m2-single-tenant'` 是常量标签，不是具体 app 租户绑定。worker scope 校验调用者后，仍应与
该库固定绑定的 tenant_public_id 相等；第二个合法租户也须被拒绝，避免两个租户都使用同一常量/本地 asset。
给绑定字段、初始化/验证责任与“两租户同 hash”反例，勿以“单应用”替代绑定条件。

这些问题不影响独立计算门启动，仍阻挡 C3/M2 DDL 授权。

## 五、round-153 交接

建议文件：

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-153-dsh-P0-2计算与聚合实现.md`

- 按 §三实现并测试 C1-b/c；选择器源码和事实层保持冻结，仅补 GV5 修订完整对象测试；
- R152-1/2 仅文档回修，不实施 M2/SKU DDL 或消费适配；
- C2 核心/fb 三键、SKU append-only 方案与其他通过项沿用，下一轮独立验收计算门后再裁决写入门。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-152-->
