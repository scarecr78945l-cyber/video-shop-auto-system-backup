"""M3 自动素材优化模块 · 公共骨架与三路管线命名空间。

对齐方案文档 06-自动素材优化模块设计.md：
- copywriting/  文案管线（标题/口播稿/投放文案/角标）—— 子代理-A
- images/       主图/详情图管线（Kimi 规划 + Wan 生图 + 质量门禁 + 类目记忆）—— 子代理-B
- video/        视频二创流水线（LLM 拆解 + 模板二创 + ffmpeg 出片）—— 后续
- review/       审核闸门 —— 后续
- ab/           A/B 优化闭环 —— 后续
- upload/       小店素材库上传（UploadService 双轨 api|ui|semi）—— 后续
"""

from __future__ import annotations

__version__ = "0.1.0"
