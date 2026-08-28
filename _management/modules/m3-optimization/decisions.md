# M3 自动素材优化 · 决策记录（decisions）

> 记录本模块关键技术决策：决策内容、理由、备选方案、日期、决策人。

| 日期 | 决策 | 理由 | 备选方案 | 决策人 |
|---|---|---|---|---|
| 2025 体系建立日 | 表前缀统一 `opt_*`，一模块一库 `m3-optimization.db` | 宪法第 4 节防数据污染；避免与 asset_*/ad_* 冲突 | 复用既有表 | 总工 |
| 2025 体系建立日 | M3 产出物写自有 opt_* 表，M2 `assets` 只读引用；evaluation 由 M3 计算落 opt_evaluation_feedback，assets.evaluation 由总控协调同步 | 评估标签口径单一来源，防双写脏数据 | M3 直写 assets | 总工 |
| 2025 体系建立日 | 视频出片用 ffmpeg/ffprobe 子进程直调（非 moviepy），出片后强制 ffprobe 硬规格校验并留证据 JSON | 硬规格是平台红线，校验可观测；子进程便于批量并发与断点续跑 | moviepy 封装 | 总工 |
| 2025 体系建立日 | LLM 密钥一律环境变量（DEEPSEEK_API_KEY / KIMI_API_KEY / WAN_API_KEY），日志 _redact_text 脱敏 | 宪法第 4/8 节 + P-004 | 配置文件存密钥 | 总工 |
| 2025 体系建立日 | **待总控裁定**：09 文档既有表 image_batches/image_assets 与 M3 生图职责的归属（生图代码按 03 归 M3 复用，但表列为「现有/复用」） | 避免表语义冲突与双写 | ① M3 全新建 opt_image_*（当前规划）② M3 接管迁移既有表 ③ M1 保留、M3 只读 | 总工（待总控） |
| 2025 体系建立日 | **待总控确认**：小店素材库上传方式——先验证 OpenAPI 素材上传接口，无则 Playwright UI 兜底，再降级半自动（系统预填人工点上传） | 上传是 M3 全自动关键节点，接口能力未知 | 仅 UI 链路 | 总工（待总控） |
| 2025 体系建立日（总控裁决） | **REC-001**：图片资产域归 M3，自建 opt_image_* 表（避免与迁移包遗留表冲突）；迁移包遗留 image_batches/image_assets 由 M0 迁移时评估归档（总控已记 data-audit） | 总控裁决，明确图片资产域归属 M3 | 复用/接管遗留表 | 总控（已批准） |
| 2025 体系建立日（总控裁决） | **REC-002**：素材上传小店素材库采用双轨抽象 UploadService，配置项 `M3_UPLOAD_MODE=api\|ui\|semi`，默认 api 优先，Playwright 兜底，半自动降级；真实可用性待用户提供小店账号后实测，先 fixtures/模拟实现 | 总控裁决，接口能力未实测前不阻塞开发 | 单轨实现 | 总控（已批准） |
| 2025 体系建立日（v1.0 集成） | **集成缺口修复**：上传成功仅写 opt_upload_records、不回填 opt_video_variants.platform_material_id，导致 A/B 排序 only_uploaded 无法感知已上传素材 → 骨架 repo.py 新增 `VideoVariantRepo`（get + update_platform_material_id 幂等回填 upload_status="uploaded"），端到端集成测试演示「上传成功 → 回填 → 排序可选」闭环 | 端到端集成测试暴露（test_optimization_e2e 首跑 only_uploaded=0），闭环完整性要求 | 由 upload 子代理内部回填（改动已验收代码，不取） | 总工 |
