# 总控状态快照（会话溢出恢复用 · 2026-09-02 更新）

> 本会话因上下文溢出中断。**全部项目状态已文件化**，新会话从本文件 + `_management/` 目录即可无损恢复。
> 恢复路径：读本快照 → `_management/dashboard.md`（模块状态）→ `logs/pitfall-log.md`（P-001~P-045）→ `logs/data-audit.md`（契约 DA-001~011）。

## 一、体系与模块状态
- 管理体系：总控 + 6 总工独立会话 + 子代理（宪法 `_management/AGENT_CONSTITUTION.md`）；7 模块 m0~m6。
- 完成度：M0/M2/M4/M6 **100%** ｜ M1 **97%** ｜ M3 95% ｜ M5 75%+。
- 全量回归：sourcing 域 194 passed（v0.71）；M4 136 passed（v0.79）。
- 备份：git 标签 **v0.1~v0.81**（v0.70~v0.81 已推送 GitHub，P-044 之后改动未提交）。

## 二、核心突破（2026-09-02 · 淘宝以图搜款打通 + 高清同款全量工具）
- **Codex 攻坚成功**：淘宝识图是**两阶段状态机**——
  ① 首页点相机图标（`[data-spm="image_search_icon"]`）→ 向 `#image-search-custom-file-input` 注入 PNG/JPG → canvas 压缩 → 按钮变"搜索"（`upload-button-active`）；
  ② **必须再点一次"搜索"按钮**（`#image-search-upload-button`）→ `window.open` 跳转标准识图结果页（s.taobao.com/search?...localImgKey=...）。
- **可复用工具**：
  - 固化全量版：`_experiment/pdd-scrape/taobao_v4.py`（HD 原图剥后缀、候选标题 bigram 打分避开推荐流污染第 1 位、断点续跑、风控熔断、批次降频参数 `--interval/--batch-size/--batch-pause`）
  - 接入工具：`_integrate_real_images.py`（tb_main → 800×800 PNG 主图 main_0..4，内容嗅探格式）
  - 门禁复核：`_verify_gate_65.py`（只读跑 ListingGate，不建任务）
- **已跑 13/65 商品**（全精确同款：锅刷/洗衣粉/洗衣液/猫粮/浴室清洁/美瞳/湿巾/儿童洗发/胶带/假睫毛/垃圾袋等），**高清真实同款主图已接入** listing（800-2048px 原图 → 800×800 PNG，每商品 3-5 张真实图），M4 门禁 **61/65 通过**。
- **卡点（P-046）**：批量跑触发**淘宝登录态失效**（首页「请登录」+ 覆盖层拦截相机点击，P-002 命中），已停止自动化。剩余 **48 商品**待用户重新登录淘宝（共享 Chrome 9223）后，用 `taobao_v4.py --interval=8 --batch-size=10 --batch-pause=300` 低频续跑（断点自动跳过已完成 13 个）。
- **待补源图**：4 商品（17 保温杯/164 美瞳/165 香薰/166 铅笔）无源图（有米云 umcdn 签名 403，P-042），待有米云重采。

## 三、当前进行中 / 待办
1. **淘宝续跑（用户前置）**：重新登录淘宝 → `taobao_v4.py` 低频续跑剩余 48 商品 → `_integrate_real_images.py` 接入 → 门禁复核。
2. **有米云重采**：补 17/164/165/166 四商品源图。
3. 服务运行中：API(8001)+前端(3000)+共享Chrome(9223)+有米云(9555)。
4. 待办（需用户批准）：**M5 v1.1 半自动实投（¥50 级）**、M4 live 上架（需确认类目资质/运费模板 REC-004）、M4 契约 T1~T7 核对。

## 四、环境事实
- 共享 Chrome 9223（淘宝/拼多多已登录，有米云/抖店罗盘登录态）；有米云 umcdn 图时效签名易过期（P-036，已本地化方案）。
- **1688 风控冷却中**（P-039，阿里系）；淘宝低频操作注意（识图间隔 3s+）。
- 淘宝识图输入仅接受 PNG/JPG/JPEG（webp 需转 PNG，P-045 Codex 确认）。

## 五、新会话恢复步骤
1. 读本快照 + `_management/dashboard.md` + `logs/pitfall-log.md`；
2. **淘宝续跑**：确认共享 Chrome 9223 淘宝已登录（无"请登录"）→ `python _experiment/pdd-scrape/taobao_v4.py --interval=8 --batch-size=10 --batch-pause=300`（自动跳过已完成 13 个）→ `_integrate_real_images.py` → `_verify_gate_65.py`；
3. 其余待办：有米云重采补 4 无源图商品、M5 实投批准、M4 live 前置（资质/运费模板确认）。
