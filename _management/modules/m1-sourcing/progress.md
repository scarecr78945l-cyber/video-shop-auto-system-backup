# M1 自动选品 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。
> 更新：体系建立日（**v1.0 收官：选品全链路可测可跑，fixtures + 真实采集双通道打通**）｜ 当前迭代：**v1.0（模块级验收完成）**

## 当前任务看板

| 任务 | 负责 | 进度 | 剩余工作 |
|---|---|---|---|
| [x] 通读宪法/踩坑日志/设计文档(04/09/10/11/03)/基线代码 | 总工 | 100% | 无 |
| [x] 撰写 brief.md / risks.md / context / database / progress / decisions / BLOCKERS | 总工 | 100% | 无 |
| [x] BLOCKER-001/002/003 总控裁决（REC-006/007/008）+ 04/03 文档口径同步 | 总工 | 100% | 无 |
| [x] S1a 基线改造+DSN 切换（config/db/README） | 子代理 32dfb48b | 100% | ✅ 验收通过 |
| [x] S1b 打分扩展+白名单接线+m1 表（tables/pipeline/迁移/测试） | 子代理 58579182 | 100% | ✅ 验收通过 |
| [x] S2 投放转化回写：`ad_backfill.py` + CLI `ad-sync` + 单测 | 子代理 3e6fd497 | 100% | ✅ 验收通过 |
| [x] S3a 探测+选择器校准（fixtures 对照，page_changed 单测） | 子代理 00389792 | 100% | ✅ 验收通过（selector-log v1.0） |
| [x] S3b 校准动作实施（A1 config.selectors 迁移 / A2 有米云日期动态化 / A3 飙升榜 fixtures / A4 动态列定位） | 子代理 45e06cf4 | 100% | ✅ 验收通过（selector-log v1.1） |
| [x] S3c 真实采集联调（三源真实入库 ≤50/源、节流熔断观察、日志脱敏、fixtures 对照、验证码即停） | 子代理 c73de00e | 100% | ✅ 验收通过（三源真实入库 101 条，s3c.db 留证） |
| [x] REC-010 app_config 键名对齐（category_whitelist → category.whitelist）+ 回归 | 总工 | 100% | ✅ 108 passed 无回归 |
| [ ] S4 联调与验收（M4/M5 交换联调、日有效候选≥200 度量、打分可解释抽查） | 总工 | 30% | M5 C-2 已会签（M5 v1.0 台账）；日有效候选度量需真实数据积累 |
| [ ] S5 迭代：闸门放松、LLM 复核（可选）、PostgreSQL 迁移配合 | 总工 | 0% | v1.1+ 排期 |

## 里程碑进度

- 本模块当前完成度：**95%**（v1.0 核心链路全部验收通过；S4/S5 属 v1.1+ 持续迭代）
- 距离目标还差：S4 联调验收（依赖 M4/M5 就绪，M5 C-2 已会签）→ S5 迭代
- **v1.0 里程碑达成（选品全链路可测可跑）**：
  ① 配置化——类目白名单 app_config 运行时接线（`category.whitelist` 键，REC-010）+ 打分权重/新鲜度阈值配置化；
  ② 库——默认 DSN `backend/data/db/m1-sourcing.db`，m1_ 投放转化两表可建（幂等迁移脚本）；
  ③ 投放转化第 5 维数据闭环——M5 回写接入器 `ad_backfill`（幂等导入+审计+CLI ad-sync，C-2 契约 M5 侧已会签）+ 消费端新鲜度/弱样本过滤；
  ④ 五维打分全链路——fixtures e2e（采集 23→入池 TopN，投放转化维度生效，去重幂等）+ 打分理由逐条可解释；
  ⑤ 真实采集打通——三源（商机中心/有米云/抖店罗盘）真实入库 101 条（s3c.db），A2 动态日期/A4 动态列定位实测命中，doudian「价格带」解析 50/50，日志脱敏 PASS，无风控事件；
  ⑥ 选择器校准基线——selector-log.md v1.1（5 来源 + A1~A6 + 三源实测小节）+ page_changed 单测。

## 剩余/迭代项（v1.1+）

| 项 | 说明 | 前置 |
|---|---|---|
| A3 飙升榜 URL 回填 | 抖店飙升榜 config url_template 待登录态取真实地址回填 | 登录态/人工 |
| A6 有米云图片收敛 | S3c 实测 youmi imgs=0（行内 img 未取到 http URL，疑似 lazy/blob），inspect-page 检查商品图 DOM 后收窄选择器；alibaba/taobao 宽泛选择器收敛待实测 | inspect-page/登录态 |
| 商机中心多筛选遍历 | 机会品当前筛选仅 1 条，多筛选遍历或人工切换后可增采集量 | 人工/排期 |
| 9223 僵尸页面前置清理 | P-016：connect_over_cdp 前关闭非采集目标页（登录态不受影响），纳入 probe 前置逻辑 | 排期 |
| S4 联调 | M4/M5 交换联调（M5 C-2 已会签成立）、日有效候选≥200 度量、打分可解释抽查 | M4/M5 就绪 + 数据积累 |
| S5 迭代 | 闸门放松（类目通过率达标）、LLM 复核（可选）、PostgreSQL 迁移配合 | 数据积累 |

## 开发阶段管理方式（总控已确认 · 体系建立日）

1. 本模块总工拥有独立会话，全权管理模块开发全流程（需求→设计→排期→分派→集成→验收→迭代）。
2. 开发任务一律由总工在会话内用 `subagent` 创建子代理执行（**每任务一个子代理**，任务书自包含：背景/目标/输入输出路径/验收标准/宪法要点）；总工不批量自写代码，只负责架构设计、任务拆解、进度管理、验收与集成。
3. 子代理完成后总工必须验收（读产出、跑测试，pytest 一律 `--basetemp=".pytest-tmp-m1"`），验收不合格退回修改。
4. 子代理阻塞先由总工判断；判断不了 → 写 `BLOCKERS.md` 结束回合，总控回复后继续。
5. 子代理产出与问题登记 `agent-activity.md` 与 `BLOCKERS.md`（如有）。

---

## 总工恢复记录（新任总工接管）

- **日期**：2026-08-29
- **新任总工**：M1 自动选品模块总工程师（新任，会话恢复）
- **接管原因**：原总工代理运行环境损坏无法恢复；代码/测试/文档已备份（git v0.1~v0.38 + GitHub），无损失。
- **模块状态确认**：
  1. 通读宪法（角色/交付物/数据隔离/UTF-8 第 11 节/pytest 独立 basetemp 第 12 节/子代理管理第 9 节）与全局踩坑日志 P-001~P-016（含 P-016 9223 僵尸页面）；
  2. 模块交付物齐全且一致：brief.md（v1.0 实现快照 108 passed）、risks.md（R-01~R-54）、decisions.md（D-0~D-9，REC-006/007/008/010 已裁决落地）、context/README.md（数据字典/C-1~C-4 契约/S3c 实测环境事实）、database/README.md（m1_ 两表 DDL + 迁移记录）；
  3. 代码现状：`backend/sourcing/` 26 个 py 文件齐备（三源采集/合规/打分/回写/调度/CLI），config.py 默认权重/白名单/REC-007 DSN 在位；
  4. **进度确认：v1.0 已 95%**——S1~S3c 全部验收通过（三源真实采集 101 条入库、s3c.db 留证）、REC-010 键名对齐已执行、sourcing 域 108 passed（`.pytest-tmp-m1`）；
  5. 剩余：S4 联调（30%，M5 C-2 已会签，依赖 M4/M5 就绪 + 数据积累）、S5 迭代（0%，v1.1+ 排期）；v1.1+ 迭代项：A3 飙升榜 URL 回填、A6 图片/宽泛选择器收敛、商机中心多筛选、9223 僵尸页前置清理、S4/S5；
  6. C1 迁移（hard-block-policy.json 等 old-system-assets）由独立子代理执行中，与本模块无冲突。
- **当前迭代**：v1.0（模块级验收完成，95%）｜ **本回合动作**：恢复确认 + 台账登记，无代码改动。
- **后续动作**：等总控派发下一批任务（v1.1+ 迭代或 S4 联调排期）。

---

## P2 数据知识吸收（2026-08-29 · P2-6/P2-7 完成）

| 任务 | 内容 | 状态 |
|---|---|---|
| [x] P2-6 榜单目录补全 | 考古加第四源备胎登记（config.py `kaogujia`，5 榜 URL 照旧系统 kaogujia_board_catalog.py，`enabled=False`）；抖店罗盘旧榜单目录登记（doudian.boards 扩展 4 榜：商品卡榜/短视频榜/同行低退榜/实时爆品挖掘榜，`enabled=False` + url_template 留空）；context/README 第六节知识档案 | ✅ 完成（D-11） |
| [x] P2-7 契约字段对照 | 对照旧系统 contracts.py（SourcedProduct/AlibabaMatch/UploadResult）统一字段命名：**以新系统命名为准不实际改名**；models.py SourceItem/Quote 加对照注释；差异登记 decisions.md D-10；context/README 第六节映射表 | ✅ 完成（D-10） |

- **验收**：sourcing 域测试 **123 passed**（`.pytest-tmp-m1`，16 文件，7.36s）全绿，fixtures 无回归。
- **全量回归观察（提请总控）**：误跑全量 `python -m pytest tests` 得 1212 passed / 3 failed / 2 skipped——3 个失败均与 M1 无关：`test_materials_archive.py` ×2（NotADirectoryError：Windows 文件名含冒号 `1688:55`，M2 域既有环境问题）、`test_ads_fixtures.py` ×1（AttributeError，M5 域）——建议总控全量回归时以 `.pytest-tmp-verify` 复跑确认，若仍失败转达 M2/M5 总工。

---

## v1.1+ 迭代看板（2026-08-29 派发 · 5 个子代理并行）

| 任务 | 子代理 | 状态 |
|---|---|---|
| [x] v1.1-① A3 飙升榜 URL 回填（config.py doudian.boards[1] url_template + kind=realtime，真实 URL 探测） | 39e20fe1 | ✅ 验收通过（175 合并回归内） |
| [x] v1.1-② A6 选择器收敛（youmi 图片 lazy 提取收敛 + alibaba/taobao 防御性收敛 + 单测） | a85a109f | ✅ 验收通过（175 合并回归内） |
| [x] v1.1-③ 9223 僵尸页清理（P-016 防复发：zombie_clean 能力 + CLI 接线 + mock 单测） | c77f21c7（中断，产出落盘后总工验收） | ✅ 验收通过（175 合并回归内） |
| [x] v1.1-④ S4 日有效候选度量（report.py daily_effective_candidates ≥200 达标标志 + CLI + 单测） | workflow m1-s4-daily-metric（subagent 2 次零产出后改投 workflow） | ✅ 验收通过（175 合并回归内） |
| [x] v1.1-⑤ S5 闸门放松配置（app_config 键 gate.relax.* + should_relax_category + dry-run CLI + 单测） | 44e9f768 | ✅ 验收通过（175 合并回归内） |

- 验收标准：sourcing 域测试全绿（`.pytest-tmp-m1`）+ fixtures 无回归；每项完成后总工验收并落盘本看板与台账。

## v1.1+ 验收记录（2026-08-29 · 五项全部通过 · v1.1 迭代收官）

- **最终合并回归**：`python -m pytest`（20 文件 = 16 基线 + test_youmi_image_extract + test_report_daily + test_zombie_clean + test_gate_relax，含 A3 doudian 改动）→ **175 passed**（`.pytest-tmp-m1`，11.76s）全绿，fixtures 无回归。
- **v1.1-① A3（本轮验收）**：飙升榜真实 URL 回填 `https://compass.jinritemai.com/shop/chance/rank-shop`（CDP 9223 登录态实测：店铺榜单页内「飙升榜」tab，与商品榜 rank-product 不同页、店铺维度榜单，kind=realtime）；doudian.py 新增 BOARD_TABS + `_ensure_board_tab`（精确文本 dispatchEvent 点 tab、未命中 PAGE_CHANGED、等待 3s 防首载竞态）+ `_locate_columns` 店铺榜表头适配（排除「商品曝光人数/点击/TOP」指标列、成交订单数→sales）+ 跳过「未上榜」占位行 + raw.shop 动态列（原硬编码 2）；真实冒烟 collect_board("飙升榜", limit=5) → 5 条店铺数据（title=店铺名/price=用户支付金额/sales=成交订单数/imgs=1）无风控；P-016 处理：playwright 挂起后经 CDP /json/close 非目标页 + node 原生 WebSocket CDP Target.createTarget 新建罗盘页探测成功（未动原 rank-product 页）；遗留：原 rank-product 目标页渲染进程无响应，建议人工刷新/关闭重开。
- **v1.1-② A6**：youmi `_extract_images` 重写（LAZY_IMG_ATTRS src→data-src→…→srcset，`_first_http_url` 过滤 data:/blob:/相对路径，收窄商品列容器，修复 S3c imgs=0）；alibaba/taobao 精确优先 + 宽泛代码兜底收敛；test_youmi_image_extract.py 15 用例 + test_collector_config +3；selector-log A6 行 ✅/🔲。
- **v1.1-③ 僵尸页**：`zombie_clean.py`（clean_zombie_targets：CDP HTTP /json/list+/json/close，幂等/容错/防御性中止/只连本机/短超时 4s/不碰凭据）+ cli `zombie-clean` 命令 + probe-browsers 前置接线 + context README P-016 防复发小节；test_zombie_clean.py 纯 mock 不连真实浏览器。
- **v1.1-④ S4**：`report.py::daily_effective_candidates(days)`（日有效候选 state∈pool/manual_review、事件/运行计数、≥200 target_met+gap、空数据容错）+ cli `report-daily` + test_report_daily.py 6 用例 + context「S4 日有效候选度量」口径小节。
- **v1.1-⑤ S5**：`gate.py`（gate.relax.* 五键点分隔命名空间、load_gate_relax_config 类型回落不抛、decide_relax 纯判定 reasons 可解释、should_relax_category、relax_manual_review dry-run 默认）+ pipeline 接线（_relax_manual_review 放行理由落 compliance.reasons 审计、PipelineResult.gate_relaxed）+ cli `gate-relax` + models.py 加法字段 + test_gate_relax.py 16 用例 + context 第七节 + decisions D-12；口径对齐 R-54/10 文档第五节（95%×50，窗口 30 天）。
- **v1.1 迭代收官**：模块完成度 **95% → 97%**（v1.1+ 五项全部落地：A3/A6 实测落地、僵尸页防复发工具化、S4/S5 工具化完成）；剩余：S4 联调实测验收（依赖真实数据积累、日有效候选≥200 需运行期验证）、A6 真实页面校准（登录态）、S5 闸门放松运行期启用（数据达标后 app_config 开闸）。

## P-028 1688 以图搜款真实链路修复（2026-08-31 · 总控直接执行 · 用户提问驱动）

- **触发**：M1 全源真实采集验证（run-pipeline --mode auto）时，用户观察浏览器提问「光上传图片不搜的吗」——1688 询价上传图片后无结果入库。
- **根因（已实测证实）**：1688 首页 `set_input_files` 上传**确实触发搜索**，但页面**跳转**到独立搜图页 `air.1688.com/kapp/1688-search/pc-image-search/?imageAddress=<图URL>`；旧结果选择器 `.card-item, [class*='offer'] li`（首页推荐位结构，2024 改版）匹配 0 行 → 误判 PAGE_CHANGED → 询价全失败（上轮 0 供应商）。纯色测试图另触发首页「推荐位」卡片（无商品链接），与真实搜图结果页不同。
- **修复（alibaba.py + config.py + 测试）**：
  1. **air 搜图直链免上传**：`_build_search_url` 直接导航 `air.1688.com/kapp/1688-search/pc-image-search/?imageAddress=<quote(图URL)>`（实测 2s 渲染 60 卡片，弃用首页上传路径）；
  2. **offerId 提取**：`_offer_id_from_row` 从卡片 `data-renderkey`（`1_0_normal_b2b-<uid>_<offerId>`）/`data-aplus-report` 末段数字提取 → 直链 `detail.1688.com/offer/<id>.html`；
  3. **detail 读价**：`_read_detail_price` 读 `.price-info/.price-comp` 多档取最小（实测 ¥8.00）；订单确认页读价降级为 `_read_order_confirm_price` 失败静默回退（SKU 浮层结构不稳定）；
  4. **选择器校准**：`result_row`=`[class*='searchOfferItem']`、`result_title`=`[class*='titleText']`、`supplier_name`=`[class*='shopName']`、新增 `search_url`/`detail_price`（config.py 同步，A1 逐键一致）；
  5. **真实冒烟**：1 条有效报价（供应商/标题/¥8.0/详情链接齐全）。
- **测试**：test_alibaba_image_search.py +8 例（build_search_url/offer_id/read_detail_price/quote 全流程 mock/无结果 PAGE_CHANGED/登录浮层 AUTH_REQUIRED）+ test_collector_config.py +2 例（P-028 选择器一致性 + read_detail_price 最小化）→ **sourcing 域 194 passed**（175 基线 + 19 新增，`.pytest-tmp-m1`）全绿无回归。
- **登记**：pitfall-log P-028、selector-log 第 4 节「P-028 校准」。

## M1 全源真实采集验证（2026-08-31 · run-pipeline --mode auto --no-quotes · 快照待办②完成）

- **结果**：采集 **230 条**（商机中心 1 + 抖店商品榜 109 + 飙升榜 120）→ 去重后 **223** → 候选 223（拒 0/人工 0）→ **入池 20**（TopN，264.6s）；真实数据全部落库（products 224 / events 232 / runs 9）。
- **有米云（第三源）**：登录态失效（AUTH_REQUIRED，两次运行一致）——采集器**正确转人工不硬闯**（P-002 纪律）；需用户在 9555 有米云浏览器重新登录后重跑补采。
- **询价链路**：独立验证 **3/3 成功**（真实商品图 → air 直链 → offerId → detail 读价 → ¥1.0/¥1.0/¥8.0 有效报价，供应商/标题/详情链接齐全）。
- **运行期问题登记**：pipeline 内多商品询价循环偶发挂死（playwright driver 稳定性，P-029）——本轮回调为 `--no-quotes` + 独立询价两步；后续排期询价子进程隔离。
- **配套改动**：`quoting_max_items=10` 配置（单轮询价商品数上限，fixtures 不受限）；cell() evaluate → text_content（带超时）；zombie-clean keep 片段补 product-rank（P-016 工具校准）。

## P-030 飙升榜店铺数据污染修复（2026-08-31 · 用户提问驱动）

- **触发**：全源验证后用户查看入池商品，提问「怎么还会有店铺的，这不是商品吗」——入池出现「认养一头牛旗舰店」「盒马官方旗舰店」等店铺名。
- **根因**：抖店「飙升榜」（rank-shop）为**店铺维度榜单**，采集器把店铺名当商品标题入库（A3 校准已知榜单结构，未把关数据语义），120 条店铺名污染商品池。
- **修复**：① config 飙升榜 `enabled=False`（live 不再采集/入池）；② 清理存量污染（删除 116 店铺商品 + 120 evidence + 120 events，保留商品榜 108 真实商品）；③ fixtures 保留飙升榜样本回放（离线模拟数据不受影响，`boards` 覆写）；④ 店铺趋势洞察/「TOP成交商品」列提取排期。
- **验证**：单源 live 只采商品榜 109 条（飙升榜跳过），重复商品被指纹去重拦截（0 新增）；sourcing 域 **194 passed** 全绿（`.pytest-tmp-m1`）。
- **登记**：pitfall-log P-030、config 注释、decisions。

## P-031 「能做品类」边界落地（2026-08-31 · 用户裁定「只找白名单里的品，其他的不要找」）

- **背景**：用户问「能做的品类搞清楚了没有」→ 审计发现白名单 9 类未真正生效（商品类目全空、permanent_exclusion 未接入、食品/饮品混入商品池）。
- **落地**：① `category_map.py` 类目解析器（标题关键词 → 白名单 9 类，食品刻意不映射）；② compliance 接入 permanent_exclusion_terms（127 词：食品/饮品/贵金属/图书，命中 → hard_reject 先于类目映射）；③ 白名单强制升级（类目空/不在白名单 → hard_reject，原 manual_review 升级）；④ 词表修正（移除「黄金」「姜」误伤，补 76 食品词，新增 safe_permanent_context_terms 27 词豁免器具/材质）。
- **验证**：真实重跑采集 110 → 候选 1（拒 107）→ 入池 1（锅刷/厨房用品）；商品池只剩白名单内品；sourcing 域 **203 passed**（+category_map 6 + compliance 3）。
- **数据源限制**：本期抖店商品榜几乎全食品/冲饮 → 白名单内可做品少；需有米云重登 + 商机中心多筛选 + 白名单类目定向选榜（后续排期）。
- **登记**：pitfall-log P-031、dashboard、快照。

## 有米云重登补采 + P-032 claim 修复（2026-08-31 · 第三源打通）

- **有米云（9555）重登成功**：单源 live 采集 **200 条**（商品榜），三源合成后商品池 **68 个白名单品（9 类全覆盖）**——个护清洁 22（洗衣液/洗发水/洗面奶/牙膏/清洁剂）、家居日用 13（抽纸/湿巾/香薰/消毒喷雾）、厨房用品 11（锅刷/保温杯/垃圾袋/锡纸盘/切菜神器）、办公文具 8（姓名贴/彩铅/中性笔/笔记本）、服饰配件 7（美瞳/发圈）、宠物用品 3、户外运动 2、收纳整理 1。
- **P-032 claim 修复**：`claim_fingerprint` 按主键查 bug（fingerprint 非主键 → 同 run 重复指纹 UNIQUE 崩溃）→ 改按指纹列查询（幂等跳过）。
- **P-031b 词表**：补 16 词（食用盐/食盐/调味料/香料/卤料/火锅料等），修正 pool 内 2 个食品漏网（青藏湖盐/川砂仁香料），pool 68 纯白名单品。
- **验证**：sourcing 域 **203 passed**（`.pytest-tmp-m1`）全绿。
- **登记**：pitfall-log P-032。

## 68 商品批量询价 + P-033/P-034（2026-08-31 · 商品池可直接上架）

- **P-033 有米云图片载体**：商品图为 CSS background-image（`.ys-bg-img`，非 img 标签）→ `_extract_images` 新增 background 提取（style 正则 + computed 兜底，img lazy 保留兜底）；重采后 **68/68 有图**（原 67 无图）。
- **批量询价（P-034 纪律）**：子进程分块（10/块）+ 块超时 + 补跑小块（5/块）+ 重试轮 + 每商品落盘；总耗时约 2 小时（两轮）。
- **结果**：68 pool 商品 → **41 个真实成本（60%）**，毛利全部 60%+（89%×9、80%×3、78%×2、76%、75%×3、73%×3、70%×4、67%×6、60%×10）；成本/建议售价/毛利/供应商已回写 products + suppliers/sku 表（复用 repo.save_quotes + 定价阶梯）；**商品池可直接上架**（M4 输入就绪）。证据 `_management/logs/m1_quote_results_20260831.jsonl`。
- **剩余 27 个**（driver 卡住/搜图无结果）登记后续轮次补询（每商品单进程隔离列入优化）。
- **登记**：pitfall-log P-033/P-034、dashboard、快照。
