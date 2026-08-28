# 项目管理中枢（_management）

> 本目录是「总控 Agent」的持久化工作区：所有会话级记忆、跨会话状态、全局规范都沉淀在这里，任何代理重启会话后仍能恢复上下文。

## 目录结构

```
_management/
├── AGENT_CONSTITUTION.md   # 代理工作宪法（所有代理的顶层规范，开工必读）
├── README.md               # 本说明
├── master-session.md       # 总控会话日志（MSG-N 编号，只追加）
├── org-chart.md            # 组织架构 + 通讯协议 + 代理花名册
├── dashboard.md            # 总控看板（模块状态汇总，用户一屏掌握全局）
├── github.md               # GitHub 备份仓库说明与推送记录
├── modules/                # 每模块一套交付物（任务书/风险/进度/决策/上下文库/数据库）
│   ├── m0-foundation/      # M0 基座与数据治理
│   ├── m1-sourcing/        # M1 自动选品
│   ├── m2-materials/       # M2 自动收集素材
│   ├── m3-optimization/    # M3 自动素材优化
│   ├── m4-listing/         # M4 自动上架
│   └── m5-ads/             # M5 自动小店投放（商品托管）
├── logs/                   # 全局日志
│   ├── pitfall-log.md      # 全局踩坑日志（P-N 编号，防复发）
│   ├── agent-activity.md   # 代理工作台账（每人每任务）
│   └── data-audit.md       # 数据联动审计（跨模块调取登记）
└── data-exchange/          # 跨模块数据交接载体（JSON）
```

## 使用说明

- **用户**：看 `dashboard.md` 掌握全局；等待总控在会话中汇报待决策事项。
- **总工/子代理**：开工前必读 `AGENT_CONSTITUTION.md` + 本模块任务书 + 踩坑日志；收工更新进度与台账。
- **总控**：唯一执行 git 备份与 GitHub 推送；唯一向用户汇报。
