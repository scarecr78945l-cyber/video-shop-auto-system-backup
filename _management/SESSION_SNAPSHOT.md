# 总控状态快照（会话溢出恢复用 · 2026-08-31 更新）

> 本会话因上下文溢出中断。**全部项目状态已文件化**，新会话从本文件 + `_management/` 目录即可无损恢复。
> 恢复路径：读本快照 → `_management/dashboard.md`（模块状态）→ `logs/pitfall-log.md`（P-001~P-029）→ `logs/data-audit.md`（契约 DA-001~011）。

## 一、体系与模块状态
- 管理体系：总控 + 6 总工独立会话 + 子代理（宪法 `_management/AGENT_CONSTITUTION.md`）；7 模块 m0~m6。
- 完成度：M0/M2/M4/M6 **100%** ｜ M1 **97%**（真实采集验证中）｜ M3 95% ｜ M5 75%+。
- 全量回归：**1401 passed**（v0.69 后 108 sourcing passed；v0.71 sourcing 194 passed）。
- 备份：git 标签 **v0.1~v0.71**（**v0.70/v0.71 已推送 GitHub**）。

## 二、当前进行中
1. **M1 全源真实采集验证 ✅ 完成**（v0.71）：采集 230 条（商机 1 + 抖店商品榜 109 + 飙升榜 120）→ 入池 20，真实落库；1688 询价链路 P-028 修复（air 直链 + offerId + detail 读价，独立验证 3/3）；**有米云登录态失效需人工重登 9555**（AUTH_REQUIRED 转人工）；pipeline 内多商品询价 driver 稳定性登记 P-029（`--no-quotes` + 独立询价两步走）。
2. 服务运行中：API(8001)+前端(3000)+共享Chrome(9223)+有米云(9555)。
3. 待办：**有米云重登后补采第三源**、M5 v1.1 半自动实投（¥50 级，用户批准后）、M4 真实草稿（旧系统 UI 函数迁移）。

## 三、环境事实
- 凭据（仅环境变量，不入文件）：WECHAT_APPID=wx4448ca65912ac699 + Secret；DEEPSEEK_API_KEY + LLM_BASE_URL(tokenrhythm/v1) + LLM_MODEL(deepseek-v4-flash-0731)；M6 admin/admin123。
- 共享 Chrome 9223（小店后台/商机中心/抖店罗盘已登录）；**有米云 9555 登录态已失效（需重登）**；ffmpeg 9.0.1 已装。
- 前端登录：localhost:3000（admin/admin123）；API：localhost:8001。

## 四、最近决策（REC）
- P-027：1688 以图搜款唯一化（用户裁定，废弃标题搜索）。
- P-028：1688 询价改 air 搜图直链（免上传）+ offerId + detail 读价（首页上传选择器过期全失败修复）。
- P-029：pipeline 内询价 driver 稳定性（cell 用带超时 API；quoting_max_items=10；询价子进程隔离排期）。
- M5 实投：半自动方案（人工勾选提交 + 系统监控止损回写），预算三重保护。
- 旧系统上架案例：10 次尝试均未完成（UI 脆弱）；新系统双轨制解决。

## 五、新会话恢复步骤
1. 读本快照 + `_management/dashboard.md` + `logs/pitfall-log.md`；
2. 各模块继续开发：总工代理（如需）重新创建（原代理可能随会话失效）——**模块代码/测试/文档全在 git v0.1~v0.71**；
3. 优先：**有米云 9555 重登 → 补采第三源 → M5 实投/ M4 草稿**（用户批准项）。
