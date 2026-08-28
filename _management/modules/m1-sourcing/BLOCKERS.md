# M1 自动选品 · 阻塞上报区（BLOCKERS）

> 总工解决不了的问题写这里（格式见宪法第 6 节），然后结束回合，总控读取后回复。

---

## BLOCKER-001 ｜ 体系建立日 ｜ 第三选品源口径：考古加 vs 抖店电商罗盘

- **现状**：04 设计文档三源为「考古加/有米云/视频号商机中心」；`backend/sourcing` 基线实现为「抖店电商罗盘/有米云/商机中心」，**考古加采集器未实现**（无 `collectors/kaogujia.py`）。03 文档模块边界亦写「复用 playwright_kaogujia.py」。
- **已尝试**：通读 04/09/10/11/03 + config.py/collectors 工厂（`collectors/__init__.py` 无 kaogujia 分支）；判定考古加需从零开发（登录态+五榜单选择器+反爬），而抖店罗盘已实测打通。
- **我的建议**：选项②——以抖店电商罗盘为正式第三源，更新 04/03 文档对应表述；考古加降级为可选第四源（后续排期）。备选：①补考古加采集器；③两者并存。
- **需要总控/用户决策**：确认第三源口径与文档更新授权（涉及跨模块设计文档修改，需总控拍板）。

---

## BLOCKER-002 ｜ 体系建立日 ｜ 模块库默认路径切换（sourcing.db → m1-sourcing.db）

- **现状**：任务指定本模块库为 `backend/data/db/m1-sourcing.db`；基线 `config.py` 默认 `sqlite:///sourcing.db`（backend CWD 相对路径）。当前 `backend/data/db/` 为空、无旧数据。
- **已尝试**：核实 `backend/data/db` 与 backend 根目录均无 .db 文件 → 无迁移成本。
- **我的建议**：S1 直接改 `config.py` 默认 DSN 为 `sqlite:///data/db/m1-sourcing.db`（`init-db` 建新库），并同步更新 backend/README 快速开始一节。备选：保留旧默认值仅文档说明（不推荐，双库漂移风险）。
- **需要总控/用户决策**：确认修改默认 DSN + 更新 backend/README 的授权（属基线文件修改，超出单模块文档范围）。

---

## BLOCKER-003 ｜ 体系建立日 ｜ M5 回写类目口径锚点

- **现状**：打分 `ad_by_cat.get(cand.category)` 为精确匹配；M5 尚未上线，类目聚合口径未定。
- **已尝试**：在 context/README C-1/C-2 与 decisions D-3 中给出草案（以 `products.category` 为锚点，完全一致匹配）。
- **我的建议**：确认 C-2 契约草案（`roi`/`sales_amount`/`sample_count`/`period`/`generated_at`）并转达 M5 总工。
- **需要总控/用户决策**：确认契约字段与类目口径；M5 上线后由总控协调双方总工签字。

---

（暂无其他阻塞）
