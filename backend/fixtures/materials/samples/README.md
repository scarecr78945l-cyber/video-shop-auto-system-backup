# M2 素材 fixtures 回归样本（P2-1）

> 用途：去重回归（image_phash 判定）、归档/相关性判定 fixtures 链路（R-M2-17 零外网零登录态）。
> 生成方式：`python fixtures/materials/samples/generate_samples.py`（可复现；脚本入库，PNG 为合成小图）。

## 样本清单

| 文件 | 构造 | 用途（测试断言口径） |
|---|---|---|
| `dup_a.png` | 复杂图（渐变+几何色块，96x96） | 去重基准样本 |
| `dup_b.png` | `dup_a` 缩放变体（80→96px） | 与 `dup_a` phash 距离 ≤ 阈值 → **应判重** |
| `noise.png` | 随机噪声（96x96） | 与 `dup_a` 距离 > 阈值 → **应不判重** |
| `rel_a.png` | 合成「商品主图」结构 | 相关性判定样本 A（供 C3/M3 relevance 链路 fixtures 演示） |
| `rel_b.png` | `rel_a` 水平翻转+缩放变体 | 相关性判定样本 B（同商品另一视角） |

去重断言对齐 `test_materials_dedup.py` 口径：`image_phash(path)` + `is_duplicate(hamming_distance(a, b), threshold=8)`
（阈值默认 8，`config.dedup.phash_hamming_threshold`，R-M2-11）。

## 真实样本占位（待总控提取）

旧系统实战素材样本 **183 图片资产**（P2-1，第二波融合清单）位于旧系统
`E:\视频号上架系统\视频号上架系统`，**不在本工作区**（`_management/data-exchange/old-system-assets/`
仅含 7 个规则 JSON，无图片）。待总控协调提取后放入 `real/` 子目录并更新本清单：

- 期望结构：`real/<商品id>/<asset_id>.<ext>`（或按总控约定）
- 用途：真实样本去重回归（跨平台同图判定）、C3 相关性门验收素材
- 当前 fixtures 回归以本目录合成样本为准（可复现、零体积风险）
