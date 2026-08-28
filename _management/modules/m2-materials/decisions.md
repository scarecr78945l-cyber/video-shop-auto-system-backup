# M2 自动收集素材 · 决策记录（decisions）

> 记录本模块关键技术决策：决策内容、理由、备选方案、日期、决策人。

| 日期 | 决策 | 理由 | 备选方案 | 决策人 |
|---|---|---|---|---|
| 2025 体系建立日 | 09 文档新增表 `assets` 在本模块实现为 `asset_items`（前缀 asset_*） | 宪法第 4 节"模块内新增表一律加模块前缀"，避免与基座/其他模块表冲突；字段与 05 文档第四节完全对齐 | 直接命名 `assets`（违反前缀纪律） | 总工 |
| 2025 体系建立日 | 视频号采集不依赖 TikTokDownloader，自研采集器（页面层 + signer.py 直链解析层接口化） | TikTokDownloader 对视频号支持弱（R-M2-05）；视频号直链需签名解析且随版本变化，接口化可单点替换 | 强行依赖 TikTokDownloader 视频号分支（不可靠） | 总工 |
| 2025 体系建立日 | 素材存储抽象存储接口（LocalStorage → MinIOStorage），当前 file_path 用本地相对键 | MinIO 暂缺（R-M2-22），M4 才随全局迁移对象存储；抽象接口让 M4 迁移只改一行配置 | 直接硬编码本地路径（M4 迁移成本高） | 总工 |
| 2025 体系建立日 | 评估标签枚举码：exploring/efficient/potential（探索期/高效/潜力），M2 不主动写，仅 M5 回写并落 `asset_evaluations` 审计 | 跨模块口径唯一（R-M2-13）；审计留痕满足宪法第 8 节"操作留证据" | 中文直接入库（跨模块易歧义） | 总工 |
| 2025 体系建立日 | 下载中台 v0.1（子代理 F）：下载核心与 ORM 表解耦，通过 `DownloadJobRepo` 协议注入（enqueue/get_job/list_jobs/claim_next/finish_success/finish_failure/retry_job/release_claim/source_risk_control/set_source_risk_control），默认实现 `SqlAlchemyDownloadJobRepo` 延迟导入 `backend.materials.repo.AssetRepo`（未就绪时方法调用给清晰报错，集成验收由总工补跑） | 并行安全：D 在建表与 AssetRepo，F 不能等；fake repo 保证单元测试零 DB 依赖（R-M2-17） | 直接依赖 D 的 ORM（并行阻塞、耦合） | 子代理 F |
| 2025 体系建立日 | 错误码→退避基表：RATE_LIMIT 180s / TIMEOUT 60s / NO_MATCH 120s / 其他 60s；节流级 0~4 ×1/2/4/8/16（next_run_at=now+base×2^level）；AUTH_REQUIRED/VERIFICATION_REQUIRED 不自动重试转 `blocked` 等人工（P-002） | 对齐 09 错误码体系与 R-M2-06 退避策略 | 统一退避不分类（频控误伤） | 子代理 F |
| 2025 体系建立日 | 熔断：worker 内存连续失败计数 ≥2 即镜像写 `asset_sources.risk_control=1`（repo 支持时），冷却期（circuit_breaker_cooldown_seconds 默认 300s）内 claim 到的该平台任务放回队列（release_claim），冷却后自动放行一个任务当探针，成功即恢复 risk_control=0 | 对齐 R-M2-04/R-M2-21 连续失败≥2 熔断 + 探针恢复 | 仅内存熔断不持久化（进程重启熔断丢失） | 子代理 F |
| 2025 体系建立日 | 断点续传两级：`fetch_file` HTTP Range 续传（416/文件变更→放弃部分文件全量重下）；worker 按 job_id 固定 `.part` 临时文件，失败保留供下次续传，成功入库后清理 | R-M2-06 断点续传 + 宪法第 8 节断点续跑 | 每次全量下载（流量浪费、易超时） | 子代理 F |
| 2025 体系建立日 | 入队幂等口径：`source_url` 已存在且 status≠success 即视为未完成，返回既有任务（200 existing=true）；成功后可再入队新建。失败任务用 `POST /jobs/<id>/retry` 重置 | 幂等防重复（宪法第 8 节）+ 失败可重试 | 仅 queued/running 判重（failed 无法再入队） | 子代理 F |
| 2025 体系建立日 | 下载中台 HTTP API 用 Python 标准库 `http.server.ThreadingHTTPServer`，零新增依赖（requirements 无 FastAPI）；实例标识 WORKER_ID 环境变量（默认 hostname-随机后缀），多实例并行领任务靠租约互斥 | requirements 已定无 FastAPI；多实例靠 45min 租约 + lease_owner 隔离（R-M2-07） | 引入 FastAPI（违反零新增依赖约束） | 子代理 F |
| 2025 体系建立日 | `finish_success(id, file_path, md5, size, evidence)` 的 file_path/md5/size 在 SQL 实现中写入 evidence_json（asset_download_jobs DDL 无这三个独立列）；asset_id 回填由 AssetRepo 后续处理（不在下载中台职责内） | DDL 权威（database/README.md），不改表结构；内存 fake 版额外保留同名字段便于测试断言 | 给 asset_download_jobs 加列（改 DDL，需与 D/总工协调，v0.1 不做） | 子代理 F |
| 2025 体系建立日 | POST /jobs 的 priority 仅接受不落库（DDL 无 priority 列），v0.1 队列按 id 序领取；若后续要优先级排队需改 DDL | DDL 权威 | 内存 fake 按 priority 排序（与 SQL 行为不一致，v0.1 不做） | 子代理 F |
| 2025 体系建立日 | 熔断默认阈值对齐任务书「连续失败≥2」：将 D 的 config.py `circuit_breaker_failures` 默认由 3 改为 2（risks.md R-M2-04/R-M2-21 亦写 ≥2）；worker 始终读配置值，测试显式注入 2 | 任务书/风险清单口径一致 | 维持 3（偏离任务书口径） | 子代理 F |
| 2025 体系建立日 | ★总工裁定：子代理 F 对 config.py 的改动 `circuit_breaker_failures` 3→2 **予以通过**（不改回） | 09 文档第三节「连续失败 ≥2 → risk_control」与 risks R-M2-04/R-M2-21 口径一致；与 sourcing 基线（SchedulerConfig.circuit_breaker_failures=2）对齐 | 维持 3（偏离全项目口径） | 总工 |
| 2025 体系建立日 | ★总工裁定：下载中台 HTTP API 默认端口由 8787 改为 **8788**（`backend/materials/__main__.py`），并登记全局踩坑日志 P-008 | 8787 已被工作区另一服务 captcha-vision-gateway 占用（WinError 10013，子代理 F 实测）；改默认避免后续实例撞端口 | 维持 8787 由总控协调占用方（依赖外部动作） | 总工 |
