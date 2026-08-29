# 项目可视化图（总控维护）

> 全流程可视化图由总控生成与维护。**任何项目状态变化（模块进度/里程碑/备份版本/新模块）后，总控同步更新对应的 JSON 源文件并重新生成 HTML。**

## 图清单

| 图 | 文件 | 内容 | 最近更新 |
|---|---|---|---|
| 业务数据流闭环 | `business-flow.html` | 采集→选品→上架→托管→回写 主链路 + 素材旁路 + 数据契约 | 2026-08-29 |
| 系统架构与管理体系 | `system-architecture.html` | 总控/总工管理体系 + M0~M6 模块 + 数据契约层 + 外部平台 + 备份 | 2026-08-29 |

> 打开 HTML 即可交互：明/暗主题切换、缩放、节点聚焦、关系追踪、演示模式、导出 PNG/SVG。

## 更新机制（后续同步流程）

1. 修改 JSON 源文件（`business-flow.json` / `system-architecture.json`）中的节点/连接/卡片；
2. 校验 + 重新生成：
   ```bash
   node "...\archify\bin\archify.mjs" validate dataflow _management/visuals/business-flow.json --quality showcase --json
   node "...\archify\bin\archify.mjs" deliver dataflow _management/visuals/business-flow.json _management/visuals/business-flow.html --quality showcase --json
   node "...\archify\bin\archify.mjs" validate architecture _management/visuals/system-architecture.json --quality showcase --json
   node "...\archify\bin\archify.mjs" deliver architecture _management/visuals/system-architecture.json _management/visuals/system-architecture.html --quality showcase --json
   ```
3. 更新本 README 的更新记录；git 提交 + 推送 GitHub。

## 更新记录

| 日期 | 更新内容 |
|---|---|
| 2026-08-29 | 首次生成：业务数据流闭环 + 系统架构图（含 M6 前端建设中状态） |
