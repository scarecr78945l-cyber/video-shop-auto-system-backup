# evidence 目录说明

本目录保存 DSH/Codex 接力验收（P0 契约与迁移）引用的证据文件。

## 未入库的大体积文件

| 文件 | 大小（字节） | SHA-256 | 用途 | 处置 |
|---|---|---|---|---|
| `盈亏表T.xlsx` | 51,286,084 | `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C` | T9 样本清单（`docs/contracts/t9-sample-manifest.md`）引用的真实业务样本；Codex 在 round-114/119/120 复核时要求保留并标注"待裁决" | 体积约 48.9 MB，按 `.gitignore` **不入库**；文件保留在本目录，可用上表 SHA-256 校验完整性 |

说明：
- 该文件为用户提供的原始盈亏表样本，不是本项目的生成产物。
- 若需纳入版本库，建议改用 Git LFS 或外部归档，并在取样清单中登记归档位置。
- 本目录下的 `.py` 证据脚本（golden_vectors/read_cid/selfcheck_batch_*）均正常入库。
