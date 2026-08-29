# M1 自动选品 · 决策记录（decisions）

> 记录本模块关键技术决策：决策内容、理由、备选方案、日期、决策人。
> 引用待决事项编号：D-1 / D-2 / D-3（对应 brief.md 与 BLOCKERS.md）。

| 日期 | 决策 | 理由 | 备选方案 | 决策人 |
|---|---|---|---|---|
| 体系建立日 | D-0：投放转化维度「数据结构先行」落地为基线默认行为（`ad_conversion_weight=10`，无数据 `active=False` 权重折入四维，和=100） | 04 文档第三节 + 11 文档 M2 里程碑要求；基线 `scoring.py` 已实现并有 fixtures 覆盖 | 无数据时维度计 0 分（会系统性压低总分，误选） | 总工（基线延续） |
| 体系建立日 | D-1（**已裁决 REC-006**）：第三选品源口径 —— **以抖店电商罗盘为正式第三源**，考古加降级可选第四源；已授权更新 04/03 文档对应表述（已完成） | ①考古加采集器从零开发成本高（登录态+五榜单选择器+反爬）；②抖店罗盘已实测打通（Aurora 表格）且同为带货榜单，数据价值等效；③不阻塞 S1-S2 | ①补考古加采集器（第四源可选）；③两者并存 | 总控（REC-006） |
| 体系建立日 | D-2（**已裁决 REC-007**）：本模块库路径 —— **config.py 默认 DSN 改为 `sqlite:///data/db/m1-sourcing.db`**，同步更新 backend/README 快速开始；改完必须跑通既有测试（39+新增） | 旧 `sourcing.db` 无数据；单一正式开发库避免双库漂移；`init-db` 幂等建表 | 保留旧默认值仅文档说明（双路径易踩 P-005 数据污染） | 总控（REC-007） |
| 体系建立日 | D-3（**已裁决 REC-008**）：M5 回写契约批准 —— 以 `products.category` 为锚点**完全一致匹配**；字段 `roi`/`sales_amount`(分,int)/`sample_count`/`period`/`generated_at`；已记 data-audit DA-001 口径（金额=分）；M5 上线后由总控协调双方签字 | 打分 `ad_by_cat.get(cand.category)` 精确匹配；类目名不一致则回写全部落空 | 类目映射表 `category-registry.json`（成本高，首版不做） | 总控（REC-008） |
| 体系建立日 | D-4（已定）：跨模块投放转化数据**不建 `ad_report_snapshots` 同名表**，改建 `m1_ad_conversion_cache`（本地缓存+审计） | 宪法第 4 节一模块一库 + 第 5 节只读纪律；M5 表归 M5 库 | 本模块直接读 M5 库（违规） | 总工 |
| 体系建立日 | D-5（已定）：新增表一律 `m1_` 前缀；回写导入以 `(source_file, period_start, period_end, generated_at)` 唯一键幂等 | 宪法第 4 节 + 09 文档幂等纪律 | 无唯一键（重复导入污染） | 总工 |
| 体系建立日 | D-6（已定）：风险登记采用 R-<n> 编号体系，与全局 P-<n> 编号并行（R 为模块内预判，P 为全局踩坑） | 避免与 P-001~P-007 冲突；risks.md 引用 P 编号不重复登记 | 直接并入 P 编号（跨模块编号需总控维护，成本高） | 总工 |
| 体系建立日 | D-7（已定）：S1a（基线 DSN 切换）与 S1b（打分扩展+接线+m1 表）**并行派发子代理**；S2（ad_backfill）与 S3（真实采集）随后 | 总控建议 S1a/S1b 并行；两任务文件范围无重叠（S1a: config/db/README，S1b: tables/pipeline/迁移/测试），避免写冲突 | 串行执行（慢一轮） | 总工（依总控批准） |
| 体系建立日 | D-8（**已裁决 REC-010**）：app_config 键名对齐 —— `category_whitelist` → **`category.whitelist`**（M0 DA-008 定稿键名） | M0 数据字典定稿会签（DA-008）统一 app_config 键名约定（点分隔命名空间）；M1 原实现下划线键名与之不一致 | 维持下划线键名（与 M0 基准不一致，会签不成立） | 总控（REC-010） |
| 体系建立日 | D-9（已定）：REC-010 执行范围与时机 —— 改 `pipeline.py` 第 57 行键名 + `test_compliance_appconfig.py` 测试键名 + `context/README.md`（C-1/环境事实）契约；**执行时机=S3c 验收后**（总控指示），执行后跑 sourcing 域回归（108+ 用例，`.pytest-tmp-m1`） | 总控指示「S3c 验收后一并执行」；改动小（3 处）无并行冲突 | S3c 期间执行（可能干扰真实采集进程读取中间态） | 总工 |
| 2026-08-29 | D-10（P2-7 契约字段对照结论，已定）：对照旧系统 `contracts.py`（SourcedProduct/AlibabaMatch）统一字段命名 —— **以新系统命名为准，不改现有字段/库 schema**（108 测试 + 库已稳定），差异全部登记。①`SourceItem`↔`SourcedProduct`：image_url→image_urls(list)、name→title、sales_rank→rank、source_url→(source+board+platform_item_id)+raw["source_product_url"]、price_range(str 区间)→price(float 元，区间如需保留入 raw)；②`Quote`↔`AlibabaMatch`（语义=匹配 vs 询价）：url→raw_url、purchase_price→unit_cost、missing_fields→missing_attrs（REC-迁移-02 已对照）、sku_summary→sku_name（近似）；③旧系统独有未建模：score/match_score、material、dropshipping_supported、product_attrs、customer_service_questions/targets（归 M4 C2 客服补参）、image_offer_candidates —— 后续扩展按本映射命名；④`UploadResult` 属 M4 上架边界，M1 不建模。已同步 models.py 对照注释 + context/README P2-7 小节 | 吸收旧系统契约知识、防字段命名漂移；新系统命名已定稿且被上下文库文档化（宪法 8.6 文档同步） | 实际改名对齐旧系统（破坏 108 测试与库 schema，无收益） | 总工 |
| 2026-08-29 | D-11（P2-6 榜单目录补全，已定）：①考古加（kaogujia）**第四源备胎**在 config.py 登记（5 榜 URL 照旧系统 kaogujia_board_catalog.py，`enabled=False` 不参与采集/调度；采集器未实现，启用前置=实现采集器+登录态+选择器校准）；②抖店罗盘**旧系统榜单目录**（3 类目×3 时间窗×3 静态榜+1 实时榜=30 组合）登记为 doudian.boards 扩展（商品卡榜/短视频榜/同行低退榜/实时爆品挖掘榜，`enabled=False` + url_template 留空，不展开类目×时间窗矩阵）；③旧系统罗盘 URL 同为 rank-product 页内 tab 切换（playwright_douyin_compass.py 实证 COMPASS_URL 单一） | P2-6 吸收旧系统榜单目录知识；enabled=False 保证零副作用（base.boards 过滤 enabled）；url_template 留空避免污染采集器 URL 映射 | 全量展开 30 组合为 boards（污染账本/调度，与现行「商品榜/飙升榜」实现冲突） | 总工 |

> 新决策持续追加；跨模块决策（D-1/D-3）已按 REC-006/007/008 落地（04/03 文档已同步），回写 `data-audit.md` 并保持 context/README 契约一致。BLOCKER-001/002/003 均已裁决关闭。**REC-010 已批准，执行中（待 S3c 验收后落地）**。
