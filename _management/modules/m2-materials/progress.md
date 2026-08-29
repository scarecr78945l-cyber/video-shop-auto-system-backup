# M2 自动收集素材 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。
> 里程碑对齐 11 文档 M1「基座+素材闭环（1–2 周）」。

## 当前迭代：v0.1（筹备）— 进行中

| 任务 | 负责 | 进度 | 剩余工作 |
|---|---|---|---|
| [x] 通读必读文档（宪法/踩坑日志/05/09/10/11/03/backend README） | 总工 | 100% | 无 |
| [x] 撰写任务书 brief.md（目标/范围/交付物/里程碑） | 总工 | 100% | 总控验收 |
| [x] 风险预判 risks.md（R-M2-01~24，覆盖签名反爬/登录态/视频号弱支持/ffmpeg/版权/存储/去重准确率） | 总工 | 100% | 总控验收 |
| [x] 数据字典 context/README.md（Asset 字段/双去重/硬规格/评估标签/契约/环境事实） | 总工 | 100% | 总控验收 |
| [x] 库 Schema 规划 database/README.md（asset_* 7 表 DDL） | 总工 | 100% | 开发阶段建库 |
| [x] 制定开发排期（子代理拆分方案） | 总工 | 100% | 待总控批准后派发 |
| [ ] 子代理任务书撰写（A~F 六个子代理） | 总工 | 100% | 全部已撰写并派发（D/F/E/C/A；B 待批次 3） |
| [x] `materials` 包骨架 + 建库（asset_* 表） | 子代理 D | 100% | ✅已验收：总工复跑 82 passed，init-db 幂等/唯一约束齐备 |
| [x] 素材下载中台（多实例 HTTP API/断点/节流熔断） | 子代理 F | 100% | ✅已验收：总工复跑 101 passed + 真实库集成冒烟全过；默认端口已改 8788（P-008） |
| [x] 双去重器（视频 MD5+关键帧 phash / 图片 phash） | 子代理 E | 100% | ✅已验收：总工唯一 basetemp 复跑 55 passed（dedup+tables+repo）；phash 与 sourcing 逐位一致，阈值 8 校准 |
| [x] ffmpeg 标准化器（硬规格校验+转码+元数据） | 子代理 C | 100% | ✅已验收：总工复跑 33 passed/1 skipped，exit 1 清晰报错；mock 模式，ffmpeg 环境待确认（就绪后自动切真实 runner） |
| [x] TikTokDownloader 二次封装（抖音/快手/小红书） | 子代理 A2 | 100% | ✅已验收：总工复跑 34 passed（basetemp .pytest-tmp-m2）；版本锁定 4.1.x，TikTokDownloader 环境待确认（就绪后装二进制即可用） |
| [x] 视频号采集器（自研签名+直链） | 子代理 B1 | 100% | ✅已验收：总工复跑 28 passed + CLI rc=0（fixtures JSON 合法）；signer.py 接口化（Mock 注入生效/Real 未校准清晰报错），auto 待登录态校准 |
| [x] 淘宝/1688 商品视频与同款图采集 | 子代理 B2' | 100% | ✅已验收：总工复跑 34 passed + CLI exit 0；降级（R-M2-08）/page_changed 证据（P-003）/脱敏抽查合格；⚠️fetch_* 半成品不在工作区已记录，auto 待登录态 |
| [x] 考古加/有米云榜单图缓存（IMAGE_CACHE） | 子代理 B3 | 100% | ✅已验收：总工复跑 25 passed（.pytest-tmp-m2）；缓存键/幂等/失败隔离锁定；多源接口 kaogujia 预留 |
| [x] 标签化 + 合规预审（供应链词/品牌词） | 子代理 B4-1 | 100% | ✅已验收：总工复跑 31 passed；词库 import 复用 sourcing.compliance（is 断言锁定），mark_disabled 幂等 |
| [ ] 单元测试（--basetemp=".pytest-tmp-m2"，宪法第 12 节） | 各子代理 | 0% | 随功能配套 |
| [x] 与 M3/M5 数据联动契约联调（evaluation 回流/上传素材库） | 子代理 B4-2 | 100% | ✅已验收：总工复跑 17 passed；DA-004 已登记 data-audit；上传抽象 mock，真实待登录态 |
| [x] 素材流水线编排 pipeline.py（v1.0 集成支撑） | 子代理 B4-3 | 100% | ✅已验收：总工复跑 19 passed + 全 M2 套件 318 passed/1 skipped；run_source 八步编排 + daily_stats |
| [x] 修复任务：test_daily_stats_aggregation（总控全量回归报告） | 总工 | 100% | ✅判定 P-015 并行写文件中间状态误报（非代码缺陷），单独/文件级/全 M2 复跑全绿，无需改代码 |
| [x] 集成验收（素材库可入库/去重/预览，日采集量可观测） | 总工 | 100% | ✅v1.0 验收通过：CLI 端到端（FixtureDownloader+MockNormalizer）RUN1 passed=2 入库、RUN2 同批重跑 deduped=2、daily-stats 聚合正确、pool 预览 2 条（compliance=passed+tags 自动生成） |
| [x] **相关性门入库质量门（REC-迁移-03 C3，M2 侧 · v1.1）** | 门禁迁移子代理（验收待总工） | 100% | 无（asset_items.relevance_status pending/passed/failed/manual_review 默认 pending + CHECK + 索引；repo create/list/update_relevance_status 幂等；integration.RelevanceGateService 消费 M3 判定（pass→passed/reject→failed/manual_review→manual_review），is_ready_for_chain 仅 passed 放行进入询价/上架链；表/repo/service 11 用例全绿；全 M2 套件 **329 passed, 1 skipped** 零回归；契约 DA-010 + data-exchange JSON） |

## 里程碑进度

- 本模块当前完成度：**100%**（筹备 15% + 批次 1~4 各 15% + 集成验收 25%：全部组件 + 流水线编排 + 集成验收完成；+C3 相关性门入库质量门 v1.1）
- 里程碑达成：`asset_* 表可建` ✅、`下载中台可跑` ✅、`双去重可用` ✅、`ffmpeg 标准化器（mock）` ✅、`TikTokDownloader 封装（fixtures）` ✅、`视频号采集器（fixtures+signer 接口化）` ✅、`淘宝/1688 采集（fixtures+降级）` ✅、`榜单图缓存` ✅、`标签化+合规预审` ✅、`M3/M5 数据联动（evaluation 回流+上传抽象）` ✅、**`v1.0 集成验收：素材库可入库/去重/预览、日采集量可观测` ✅**、**`C3 相关性门入库质量门（relevance_status 四态 + 预检接口）` ✅**
- 环境待确认（不影响 v1.0，就绪后自动启用）：**ffmpeg 未安装**（标准化器/视频关键帧抽帧 mock→真实，就绪自动切）、**TikTokDownloader 未安装**（就绪装 4.1.x）、**共享浏览器登录态**（三采集器 auto 模式待登录态+选择器/签名抓包校准）、**小店素材库上传 API/登录态**（MATERIALS_UPLOAD_MODE=shop 切换）、**Qwen-VL 相关性判定真实模式**（relevance.mode=auto，API Key 就绪自动启用，M2 侧仅消费结果不受影响）
- 全 M2 套件基线：**329 passed / 1 skipped**（`.pytest-tmp-m2`，宪法第 12 节；v1.0 基线 318 + C3 新增 11）

> 测试纪律（宪法第 12 节）：pytest 一律 `--basetemp=".pytest-tmp-m2"`；全量回归由总控统一执行。

## 开发阶段管理方式（总控已确认，M2 全流程遵守）

1. 总工在自己的会话内用 `subagent` 工具创建子代理承担具体开发任务（**每任务一个子代理**，任务书自包含：背景/目标/输入输出路径/验收标准/宪法要点含编码纪律与 P-001）。
2. 架构设计、任务拆解、进度管理、验收与集成由**总工负责，不把批量开发任务留给自己写**。
3. 子代理完成后总工**验收**（读产出、跑测试，命令带独立 basetemp `--basetemp=".pytest-tmp-m2"`，宪法第 12 节），不合格退回修改。
4. 子代理阻塞先由总工判断；判断不了 → 写 `BLOCKERS.md`（宪法第 6 节格式）并结束回合，总控回复后继续。
5. 总工不得运行 git 命令；不得读写其他模块库；不得写明文密钥。

## 后续排期（可拆子代理任务）

> 对齐 brief.md 第五节。子代理按宪法第 9 节自包含任务书派发（后台运行），总工验收。

| 批次 | 任务 | 子代理 | 预计依赖 |
|---|---|---|---|
| 1 | 素材库表 asset_* DDL + repo 层建库 | D | 无（schema 已规划） |
| 1 | 下载中台（HTTP API/断点/节流熔断） | F | 错误码体系（M0 已定义） |
| 2 | 双去重器（视频/图片指纹） | E | D 的表结构 ✅已就绪；fixtures 校准阈值 |
| 2 | ffmpeg 标准化器 | C | ⚠️ffmpeg 未安装（环境待确认）→ mock 模式实现，就绪切换 |
| 2 | TikTokDownloader 二次封装 | A | ⚠️TikTokDownloader 未安装（环境待确认）→ 锁定版本设计+fixtures 测试 |
| 3 | 视频号采集器（签名+直链） | B | 共享浏览器登录态（P-002）；signer 接口化 |
| 3 | 淘宝/1688 采集复测 + 榜单图缓存 | 总工直管 | sourcing 浏览器链路 |
| 4 | 标签化 + 合规预审 | 总工直管 | compliance.py 复用 |
| 4 | M3/M5 契约联调 + 集成验收 | 总工 | M3/M5 模块进度 |

## 迭代版本历史

| 版本 | 说明 | 日期 |
|---|---|---|
| v0.1 | 筹备：文档四件套（brief/risks/context/database）+ 排期 | 2025 体系建立日 |
