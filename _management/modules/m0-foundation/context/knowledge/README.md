# M0 知识库（knowledge）· 总索引

> **P2 数据知识吸收**（2026-08-29 派发，对齐《旧系统第二波融合清单》P2 档）：旧系统数据与知识资产的**只读存档区**。
> 铁律：只读存档、不写明文密钥（P-004）、引用注明来源（宪法第 4/5 节）；语料/文档分析产出物一律写入本目录新文件并登记来源。

## 目录

| 子目录/文件 | 内容 | 来源 | 用途 |
|---|---|---|---|
| `corpus/` | 业务语料：`CHAT_TRANSCRIPT_SANITIZED.md`（1.42 MB，3836 条已脱敏消息）+ `CHAT_HANDOFF.md`（6 KB）+ `corpus/README.md` 登记 | 旧系统 `docs/migration/`（P2-2） | LLM 词表扩充 / 规则抽取 / 测试用例生成 |
| `superpowers/` | 设计决策史：`specs-decisions.md`（specs 12 篇）+ `plans-decisions-01-08.md` + `plans-decisions-09-15.md`（plans 15 篇）+ 本索引 | 旧系统 `docs/superpowers/`（P2-3） | 设计决策溯源（为什么这么设计），供模块规划/评审对照 |
| （运行时产物） | MANIFEST.json 校验清单（P2-4） | `backend/foundation/manifest.py`（CLI：`python -m foundation manifest build/verify`） | 关键交付物（DDL/迁移脚本/词表）备份与交接的 SHA-256 可追溯 |

## 使用约定

1. **只读**：本目录文件不修改、不删减；引用必须注明来源与用途。
2. 从语料/文档分析产出新词表、规则、契约 → 新文件写入本目录并登记来源（如后续 LLM 词表扩充任务）。
3. 关键交付物（schema DDL / 迁移脚本 / 词表 / 语料）备份、迁移、交接前后：
   - 生成：`python -m foundation manifest build -o MANIFEST.json --base-dir <dir> --title <说明> --meta policy=<策略> file1 file2 ...`
   - 校验：`python -m foundation manifest verify -m MANIFEST.json --base-dir <dir>`（退出码 0=全通过）
   - 机制对齐旧系统 `build_material_manifest.py` + 迁移审计（P2-4）。
4. 登记纪律：本目录的增删改在 `_management/logs/agent-activity.md` 台账留痕。

## 登记

- P2-2 / P2-3 / P2-4 落盘：2026-08-29 ｜ M0 总工程师（新任）+ 子代理（P2-3 抽取）｜ 详见 `corpus/README.md`、`superpowers/` 各归档文件。
