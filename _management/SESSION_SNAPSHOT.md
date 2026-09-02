# 总控状态快照（会话溢出恢复用 · 2026-09-02 更新）

> 本会话因上下文溢出中断。**全部项目状态已文件化**，新会话从本文件 + `_management/` 目录即可无损恢复。
> 恢复路径：读本快照 → `_management/dashboard.md`（模块状态）→ `logs/pitfall-log.md`（P-001~P-045）→ `logs/data-audit.md`（契约 DA-001~011）。

## 一、体系与模块状态
- 管理体系：总控 + 6 总工独立会话 + 子代理（宪法 `_management/AGENT_CONSTITUTION.md`）；7 模块 m0~m6。
- 完成度：M0/M2/M4/M6 **100%** ｜ M1 **97%** ｜ M3 95% ｜ M5 75%+。
- 全量回归：sourcing 域 194 passed（v0.71）；M4 136 passed（v0.79）。
- 备份：git 标签 **v0.1~v0.81**（v0.70~v0.81 已推送 GitHub，P-044 之后改动未提交）。

## 二、核心突破（2026-09-02 · 淘宝以图搜款打通）
- **Codex 攻坚成功**：淘宝识图是**两阶段状态机**——
  ① 首页点相机图标（`[data-spm="image_search_icon"]`）→ 向 `#image-search-custom-file-input` 注入 PNG/JPG → canvas 压缩 → 按钮变"搜索"（`upload-button-active`）；
  ② **必须再点一次"搜索"按钮**（`#image-search-upload-button`）→ `window.open` 跳转标准识图结果页（s.taobao.com/search?...localImgKey=...）。
  之前总控反复注入（set_files/CDP/粘贴/手机UA/系统对话框）全失败，因漏了第②步（只做阶段①）。
- **可复用脚本**：
  - Codex 原版：`_experiment/pdd-scrape/codex-work/taobao_image_search_cdp.py`（单图识图→同款链接）
  - 固化版：`_experiment/pdd-scrape/taobao_v3.py`（识图→第一个同款→详情扒 8 张主图→下载，3 商品验收通过，各 57 同款）
- **实测**：#1 锅刷/#22 洗衣粉/#40 胶带 全通过；识图返回精准同款（#22 → 昕优客内衣洗衣液）。
- **待优化**：下载主图为 `_q50` 缩略图（28-80KB），需去压缩参数取高清原图；识别结果第 1 位偶混推荐流（#22 第 1 张是沐浴露、#1 第 1 张是店铺 logo），第 2 张起是精准同款——全量时应取前 N 个同款并关键词过滤。
- **下一步**：① 高清图优化；② 全量跑 65 个商品（低频 3s 间隔，约 6-8 分钟）；③ 接入主项目 `data/images/listing/<pid>/` 替换现有构图图 → M4 上架素材达标。

## 三、当前进行中 / 待办
1. **M1 三源采集打通**（v0.74）：商品池 68 白名单品（9 类）；M4 65 个 pending 上架任务待 live。
2. 服务运行中：API(8001)+前端(3000)+共享Chrome(9223)+有米云(9555)。
3. 待办（需用户批准）：**M5 v1.1 半自动实投（¥50 级）**、M4 live 上架（需确认类目资质/运费模板 REC-004）、M4 契约 T1~T7 核对。

## 四、环境事实
- 共享 Chrome 9223（淘宝/拼多多已登录，有米云/抖店罗盘登录态）；有米云 umcdn 图时效签名易过期（P-036，已本地化方案）。
- **1688 风控冷却中**（P-039，阿里系）；淘宝低频操作注意（识图间隔 3s+）。
- 淘宝识图输入仅接受 PNG/JPG/JPEG（webp 需转 PNG，P-045 Codex 确认）。

## 五、新会话恢复步骤
1. 读本快照 + `_management/dashboard.md` + `logs/pitfall-log.md`；
2. **优先推进：淘宝以图搜款全量 65 商品**（用 `_experiment/pdd-scrape/taobao_v3.py` 固化版，先优化高清图）→ M4 上架素材；
3. 其余待办：M5 实投批准、M4 live 前置（资质/运费模板确认）。
