"""M6 前端控制台 · 后端 API 层（FastAPI 应用）。

聚合 M0~M5 repo/服务能力，作为前端唯一取数通道；不改动各模块包。

- 启动：`python -m api`（backend/ 目录）或 `uvicorn api.app:app --port 8000`
- 测试：`python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"`
- 详情见 `backend/api/REPORT.md` 与 `_management/modules/m6-frontend/context/README.md`。
"""

__version__ = "0.1.0"
