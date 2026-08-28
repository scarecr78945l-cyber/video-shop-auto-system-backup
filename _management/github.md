# GitHub 备份仓库说明

> 用途：本项目的官方备份仓库（总控唯一执行 git 推送）。每一关键节点 `commit + tag + push`，保证随时可回退。

## 仓库信息

| 项 | 值 |
|---|---|
| 仓库地址 | `https://github.com/scarecr78945l-cyber/video-shop-auto-system-backup` |
| 仓库可见性 | **public（建议改 Private：Settings → Danger Zone → Change visibility）** |
| 推送方式 | fine-grained PAT（Contents: Read and write，经本地代理 127.0.0.1:7897） |

## 推送记录

| 时间 | 标签 | 内容 | 状态 |
|---|---|---|---|
| 2026-08-28 | v0.1 | 体系建立（宪法/中枢/基线） | ✅ 已推送 |
| 2026-08-28 | v0.2~v0.6 | 筹备产出/开发里程碑/纪律修复 | ✅ 已推送 |
| 2026-08-28 | v0.7 | 台账更新 + 备份推送成功 | ✅ 已推送 |

> 后续每次提交+打标签后增量推送（`git push origin --all && git push --tags`）。

## 备份纪律（对照宪法第 7 节）

1. 只推代码、文档、配置、测试、fixtures（不含数据库文件与浏览器登录态）。
2. 推送前必须验证 `.gitignore` 生效：`git status` 中不得出现 `*.db`、`chrome-profiles`、`.env`。
3. 标签命名：`v<版本>`（例：`v0.1`、`m1-v1.0`）。
4. 每次推送后在本文件与 `dashboard.md` 记录：时间、标签、内容摘要、推送状态。

## 推送记录

| 时间 | 标签 | 内容 | 状态 |
|---|---|---|---|
| 2026-08-28 | v0.1 | 体系建立（宪法/中枢/基线） | ✅ 已推送 |
| 2026-08-28 | v0.2~v0.6 | 筹备产出/开发里程碑/纪律修复 | ✅ 已推送 |
| 2026-08-28 | v0.7 | 台账更新 + 备份推送成功 | ✅ 已推送 |

> 后续每次提交+打标签后增量推送（`git push origin --all && git push --tags`）。
