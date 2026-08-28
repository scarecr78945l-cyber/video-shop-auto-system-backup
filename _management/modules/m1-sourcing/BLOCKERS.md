# M1 自动选品 · 阻塞上报区（BLOCKERS）

> 总工解决不了的问题写这里（格式见宪法第 6 节），然后结束回合，总控读取后回复。

---

## BLOCKER-001 ｜ 体系建立日 ｜ 第三选品源口径：考古加 vs 抖店电商罗盘 —— ✅ 已裁决（REC-006）

- **现状**：04 设计文档三源为「考古加/有米云/视频号商机中心」；`backend/sourcing` 基线实现为「抖店电商罗盘/有米云/商机中心」，**考古加采集器未实现**（无 `collectors/kaogujia.py`）。03 文档模块边界亦写「复用 playwright_kaogujia.py」。
- **裁决**：总控批准选项② —— **以抖店电商罗盘为正式第三源，考古加降级可选第四源**；授权更新 04/03 文档对应表述（已于 体系建立日 完成：04 文档来源表与打分数据来源、03 文档架构图采集层）。
- **状态**：关闭。后续若做考古加，作为可选第四源单独排期。

---

## BLOCKER-002 ｜ 体系建立日 ｜ 模块库默认路径切换（sourcing.db → m1-sourcing.db）—— ✅ 已裁决（REC-007）

- **现状**：任务指定本模块库为 `backend/data/db/m1-sourcing.db`；基线 `config.py` 默认 `sqlite:///sourcing.db`（backend CWD 相对路径）。当前 `backend/data/db/` 为空、无旧数据。
- **裁决**：总控批准 —— `config.py` 默认 DSN 改为 `sqlite:///data/db/m1-sourcing.db`，同步更新 backend/README 快速开始；**改完必须跑通既有测试（39+新增，pytest --basetemp=".pytest-tmp"）**。
- **状态**：执行中（S1a 子代理，id=32dfb48b）。

---

## BLOCKER-003 ｜ 体系建立日 ｜ M5 回写类目口径锚点 —— ✅ 已裁决（REC-008）

- **现状**：打分 `ad_by_cat.get(cand.category)` 为精确匹配；M5 尚未上线，类目聚合口径未定。
- **裁决**：总控批准契约草案 —— 以 `products.category` 为锚点**完全一致匹配**；字段 `roi`/`sales_amount`(分,int)/`sample_count`/`period`/`generated_at`；已记 data-audit DA-001 口径（金额=分）；**M5 上线后由总控协调双方签字**。
- **状态**：关闭（契约生效，签字环节待 M5 上线）。

---

（暂无其他阻塞）
