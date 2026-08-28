"""M2 自动收集素材 · 素材流水线编排（采集→下载→双去重→标准化→标签→合规→入库）。

对应 05 文档第二节采集流水线与 v1.0 集成验收「素材库可入库/去重/预览、日采集量可观测」：
    定时采集（采集器）→ 下载（下载中台）→ 去重（MD5+phash 双去重）
    → 标准化（ffmpeg 硬规格）→ 标签化 → 合规预审 → 入库（asset_items 终态）
    → 评估标签回流（M5 回写，本流水线不写 evaluation，见 context 1.4）

设计（本任务 B4-3；接口契约记于本文件，总工验收后同步 decisions.md）：
- 组件可注入（download_service/dedup_service/normalizer/tagger/compliance/upload），
  缺省用延迟 import + getattr 存在性检测；组件缺失时该阶段降级并标记 skipped，
  不崩整条流水线（R-M2-17：fixtures 零外网零浏览器零真实 ffmpeg 可全链路跑通）。
- 并行子代理 B4-1（tagger.py）已就绪时自动对接其真实协议，未就绪时延迟 import 兜底
  （ImportError → 组件缺失 → 跳过并标记）；本任务不创建/修改 tagger.py。对接口径（双兼容）：
    * tagger：模块级函数 `generate_tags(source_platform, source_author, title,
      category_hint, max_tags, config)`（B4-1 真实协议）或 `Tagger` 类实例的
      `generate_tags(item)`（通用协议），防御式逐级探测；
    * compliance：`MaterialCompliance(config)` 实例 —— 入库前用 `check_material(title,
      extra_text, asset_type)` 做预审门（reject → 不入终态），入库后用
      `evaluate_and_record(repo, asset_id, title, extra_text, ...)` 落证据审计；
      也兼容通用 `evaluate_and_record(item, tags) -> {"result": ...}` 协议（Mock）。
- 组件显式禁用：`MaterialPipeline(config, db=..., tagger=None, compliance=None, ...)`
  显式传 None 即强制缺失（不做延迟导入），供降级测试/断点场景确定性使用。
- 每条目流程（阶段 → 终态）：
    ① 必填校验（source_url/source_platform/asset_type 缺失 → failed）
    ② 去重预检（DedupService.check：MD5 精确；命中即 deduped；ffmpeg 缺失抽帧 → skipped 环境待确认）
    ③ 下载（DownloaderService/注入组件；组件缺失或下载失败 → failed 分类）
    ④ 去重复检（有本地文件时 MD5+phash 全量检查；ffmpeg 缺失 → skipped）
    ⑤ 标准化（Normalizer.validate/normalize；组件缺失或 ffmpeg 缺失 → skipped；硬规格不达标 → rejected）
    ⑥ 标签（tagger.generate_tags；组件缺失 → 跳过该阶段继续，不入终态计数）
    ⑦ 合规预审（MaterialCompliance.evaluate_and_record；组件缺失 → skipped 不入终态；
       reject → rejected 不入终态；pass → compliance_status=passed 终态入库）
    ⑧ 终态入库（repo.create_asset 指纹认领防并发；DuplicateAssetError → deduped 兜底）
- 统计口径（stats）：
    total        输入条目数
    downloaded   下载阶段成功条目数（阶段计数）
    normalized   标准化阶段预检通过条目数（阶段计数）
    deduped      判定重复未入库条目数（终态）
    passed       终态入库且 compliance_status=passed 条目数（终态）
    rejected     硬规格/合规拒绝未入库条目数（终态）
    failed       下载失败/必填缺失/未分类异常未入库条目数（终态）
    skipped      组件缺失/环境未就绪（ffmpeg 待确认等）而未入库条目数（终态，defer 断点续跑）
  恒等式：total = deduped + passed + rejected + failed + skipped（终态互斥，测试锁定）。
- 错误分类对齐全局码表（VERIFICATION_REQUIRED / AUTH_REQUIRED / RATE_LIMIT / TIMEOUT /
  NO_MATCH / PLATFORM_REJECT / UNEXPECTED）；errors 的 message 一律脱敏
  （redact_url 敏感查询参数 → ***；超长截断；绝不落 Cookie/密钥，P-004）。
- 幂等与断点（宪法第 8 节）：create_asset 指纹认领幂等（重复条目恒走 deduped）；
  skipped 条目可环境就绪后重跑续入（断点续跑）。
- daily_stats：日采集量统计（按 source_platform/asset_type/upload_status 聚合
  asset_items.created_at 当日，ISO8601 UTC 取日期 YYYY-MM-DD）；空库返回全零结构不崩。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional, Protocol

from sqlalchemy import select

from .config import MaterialsConfig, load_config
from .dedup import FFmpegNotFoundError
from .downloader import (
    AUTH_REQUIRED,  # noqa: F401  码表常量（供上层统一引用）
    NO_MATCH,  # noqa: F401
    PLATFORM_REJECT,
    RATE_LIMIT,  # noqa: F401
    TIMEOUT,  # noqa: F401
    UNEXPECTED,
    VERIFICATION_REQUIRED,  # noqa: F401
    redact_url,
)
from .normalizer import NormalizerError, detect_ffmpeg
from .repo import DuplicateAssetError

log = logging.getLogger("materials.pipeline")

# 错误信息截断上限（脱敏纪律 P-004：长信息截断不落全量）
_MAX_MSG = 300


def _truncate(text: Any, n: int = _MAX_MSG) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: n - 3] + "..."


# =====================================================================
# 组件协议（接口化，测试/并行子代理对接口径）
# =====================================================================
class DownloaderProtocol(Protocol):
    """下载组件协议：download(item) -> dict。

    dict 字段：{ok: bool, file_path: str, md5: str, size: int,
               error_code: str|None, message: str|None}
    """

    def download(self, item: dict[str, Any]) -> dict[str, Any]: ...


class NormalizerProtocol(Protocol):
    """标准化组件协议（对齐 normalizer.Normalizer）。"""

    def validate(self, path: str) -> dict[str, Any]: ...

    def normalize(self, input_path: str, output_path: str | None = None) -> dict[str, Any]: ...


class TaggerProtocol(Protocol):
    """标签组件协议（B4-1 tagger.generate_tags 对接口径）。"""

    def generate_tags(self, item: dict[str, Any]) -> Any: ...


class ComplianceProtocol(Protocol):
    """合规组件协议（B4-1 MaterialCompliance.evaluate_and_record 对接口径）。"""

    def evaluate_and_record(self, item: dict[str, Any], tags: Any = None, **kwargs: Any) -> dict[str, Any]: ...


# =====================================================================
# Mock / 适配组件（fixtures 全链路零外网，R-M2-17）
# =====================================================================
class MockDownloader:
    """测试/演示注入下载器：results 按 item_key 预设结果，未预设默认成功。

    results: {item_key: {"ok": bool, "error_code": str|None, "message": str|None,
                          "file_path": str, "md5": str, "size": int}}
    fail_all: 非 None 时所有条目按该错误码失败（字符串=错误码；True=UNEXPECTED）。
    """

    def __init__(self, results: dict[str, dict[str, Any]] | None = None, fail_all: Any = None):
        self.results = results or {}
        self.fail_all = fail_all
        self.calls: list[dict[str, Any]] = []

    def download(self, item: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(item))
        key = str(item.get("item_key") or "")
        preset = self.results.get(key)
        if preset is not None:
            return dict(preset)
        if self.fail_all:
            code = self.fail_all if isinstance(self.fail_all, str) else UNEXPECTED
            return {"ok": False, "error_code": code, "message": f"mock 下载失败（fail_all={code}）"}
        md5 = str(item.get("md5") or "a" * 32)
        ext = ".jpg" if item.get("asset_type") == "image" else ".mp4"
        return {
            "ok": True,
            "file_path": f"mock/{md5[:8]}{ext}",
            "md5": md5,
            "size": int(item.get("size") or 1024),
        }


class MockNormalizer:
    """测试注入标准化器：validate/normalize 返回固定结果，不依赖真实 ffmpeg（R-M2-17）。

    raise_error 非 None 时 validate 直接抛出（如 NormalizerError 模拟 ffmpeg 缺失路径）。
    """

    def __init__(
        self,
        passed: bool = True,
        failures: list[dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
        normalize_result: dict[str, Any] | None = None,
        raise_error: Exception | None = None,
    ):
        self.passed = passed
        self.failures = list(failures or [])
        self.meta = dict(meta or {})
        self.normalize_result = normalize_result or {}
        self.raise_error = raise_error
        self.validate_calls: list[str] = []
        self.normalize_calls: list[tuple] = []

    def validate(self, path: str) -> dict[str, Any]:
        self.validate_calls.append(str(path))
        if self.raise_error is not None:
            raise self.raise_error
        return {"passed": self.passed, "failures": list(self.failures), "meta": dict(self.meta)}

    def normalize(self, input_path: str, output_path: str | None = None) -> dict[str, Any]:
        self.normalize_calls.append((str(input_path), str(output_path)))
        out = str(output_path) or str(input_path) + ".normalized.mp4"
        return {
            "output_path": out,
            "passed": self.passed,
            "failures": list(self.failures),
            **(self.normalize_result or {}),
        }


class MockTagger:
    """测试注入标签器：generate_tags 返回固定标签列表。"""

    def __init__(self, tags: list[str] | None = None):
        self.tags = list(tags or ["通用"])
        self.calls: list[dict[str, Any]] = []

    def generate_tags(self, item: dict[str, Any]) -> list[str]:
        self.calls.append(dict(item))
        return list(self.tags)


class MockCompliance:
    """测试注入合规器：evaluate_and_record 返回固定结果（pass/reject/review）。"""

    def __init__(self, result: str = "pass", hit_words: list[str] | None = None, note: str | None = None):
        self.result = result
        self.hit_words = list(hit_words or [])
        self.note = note
        self.calls: list[tuple] = []

    def evaluate_and_record(self, item: dict[str, Any], tags: Any = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((dict(item), tags))
        return {"result": self.result, "hit_words": list(self.hit_words), "note": self.note}


class FixtureDownloader:
    """离线占位下载器（CLI --downloader fixtures / 演示用，R-M2-17 零外网）。

    - 条目带本地存在的 file_path → 真实计算 md5/size（fixtures 本地样本）；
    - 否则取条目自带 md5/size；md5 缺失时用 source_url 的确定性占位指纹
      （仅离线演示，真实链路请注入 DownloaderServiceAdapter）。
    """

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def download(self, item: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(item))
        path = str(item.get("file_path") or "")
        if path and Path(path).exists():
            from .dedup import compute_md5

            try:
                return {
                    "ok": True,
                    "file_path": path,
                    "md5": compute_md5(path),
                    "size": int(Path(path).stat().st_size),
                }
            except OSError:
                pass
        md5 = str(item.get("md5") or "").strip() or hashlib.md5(
            str(item.get("source_url") or "").encode("utf-8")
        ).hexdigest()
        ext = ".jpg" if item.get("asset_type") == "image" else ".mp4"
        return {
            "ok": True,
            "file_path": str(item.get("file_path") or f"fixtures/{md5[:8]}{ext}"),
            "md5": md5,
            "size": int(item.get("size") or 0),
        }


class DownloaderServiceAdapter:
    """把下载中台 DownloaderService（入队 + worker 单轮）适配为流水线 download(item) 协议。

    流程：enqueue_job → run_once(max_jobs=1) → get_job 回读终态；
    成功 → {ok, file_path, md5, size}；失败 → {ok: False, error_code, message}；
    任何异常 → {ok: False, error_code: UNEXPECTED}（不抛出，R-M2-09 失败隔离）。
    """

    def __init__(self, service: Any):
        self.service = service

    def download(self, item: dict[str, Any]) -> dict[str, Any]:
        job_type = str(item.get("asset_type") or "video")
        platform = str(item.get("source_platform") or "")
        url = str(item.get("source_url") or "")
        try:
            job, _created = self.service.enqueue_job(platform, url, job_type)
            self.service.run_once(max_jobs=1)
            job = self.service.get_job(int(job["id"]))
        except Exception as exc:
            return {"ok": False, "error_code": UNEXPECTED, "message": _truncate(f"{exc.__class__.__name__}: {exc}")}
        if not job:
            return {"ok": False, "error_code": UNEXPECTED, "message": "下载任务回读为空"}
        if job.get("status") == "success":
            return {
                "ok": True,
                "file_path": str(job.get("file_path") or ""),
                "md5": str(job.get("md5") or ""),
                "size": int(job.get("size") or 0),
            }
        return {
            "ok": False,
            "error_code": str(job.get("error_code") or UNEXPECTED),
            "message": _truncate(str(job.get("error_message") or "下载失败")),
        }


# =====================================================================
# MaterialPipeline：端到端编排
# =====================================================================
class MaterialPipeline:
    """素材流水线编排器。

    :param config: materials.config.MaterialsConfig（或兼容对象）
    :param db: materials.db.Database（缺省不建；dedup/repo 需 db 才可用）
    :param components: 可注入组件：
        download_service / dedup_service / normalizer / tagger / compliance / upload
    """

    def __init__(self, config: Optional[MaterialsConfig] = None, db: Any = None, **components: Any):
        self.config = config or load_config()
        self.db = db
        self.repo = None
        if self.db is not None:
            from .repo import AssetRepo

            self.repo = AssetRepo(self.db)
        self.components: dict[str, Any] = {
            "download_service": components.get("download_service"),
            "dedup_service": components.get("dedup_service", self._default_dedup()),
            "normalizer": components.get("normalizer"),
            "tagger": self._resolve_tagger(components),
            "compliance": self._resolve_compliance(components),
            "upload": components.get("upload"),
        }

    # ---------------------------------------------------------- 组件装配
    def _default_dedup(self) -> Any:
        """dedup 缺省：db 可用时装配真实 DedupService（双去重服务，R-M2-11）。"""
        if self.db is None:
            return None
        from .dedup import DedupService

        return DedupService(self.db)

    @staticmethod
    def _lazy_import(module: str, attr: str) -> Any:
        """延迟导入（并行子代理产出未就绪时返回 None，不抛 ImportError）。"""
        try:
            from importlib import import_module

            mod = import_module(f".{module}", package=__package__)
            return getattr(mod, attr, None)
        except ImportError:
            return None

    def _resolve_tagger(self, components: dict[str, Any]) -> Any:
        """tagger 组件：显式传 None 即强制缺失（禁用延迟导入）；缺省按 B4-1 真实协议探测。"""
        if "tagger" in components:
            return self._coerce_component(components["tagger"], "tagger")
        lazy = self._lazy_import("tagger", "generate_tags") or self._lazy_import("tagger", "Tagger")
        if lazy is None:
            return None
        return self._coerce_component(lazy, "tagger")

    def _resolve_compliance(self, components: dict[str, Any]) -> Any:
        """compliance 组件：显式传 None 即强制缺失；缺省延迟导入 MaterialCompliance（B4-1）。"""
        if "compliance" in components:
            return self._coerce_component(components["compliance"], "compliance")
        return self._coerce_component(None, "compliance", ("tagger", "MaterialCompliance"))

    def _coerce_component(self, value: Any, name: str, lazy_spec: Optional[tuple[str, str]] = None) -> Any:
        """组件归一：缺省延迟导入 → 类自动实例化（构造签名防御式探测）→ 实例原样返回。"""
        if value is None and lazy_spec:
            value = self._lazy_import(*lazy_spec)
            if value is not None:
                log.info("延迟导入组件 %s：.%s.%s", name, lazy_spec[0], lazy_spec[1])
        if value is None:
            return None
        if isinstance(value, type):
            for kwargs in (
                {"config": self.config, "repo": self.repo},
                {"config": self.config},
                {},
            ):
                try:
                    return value(**kwargs)
                except TypeError:
                    continue
                except Exception as exc:
                    log.warning("组件 %s 实例化失败（%s），按缺失降级", name, exc)
                    return None
            log.warning("组件 %s 构造签名不兼容，按缺失降级", name)
            return None
        return value

    # ---------------------------------------------------------- 流水线入口
    def run_source(self, source_platform: str, items: list[dict[str, Any]], mode: str = "fixtures") -> dict:
        """对一批采集条目执行端到端流水线，返回统计/错误/环境快照（全程异常捕获不抛出）。

        :param source_platform: 来源平台（数据字典口径，如 视频号）
        :param items: 统一 dict 列表（字段对齐 wechat_video 输出：
            source_platform/source_url/source_author/title/heat_score/video_id，
            可附加 asset_type/md5/phash/size/duration/resolution/tags）
        :param mode: fixtures（离线默认）/ auto（真实链路）
        """
        stats: dict[str, int] = {
            "total": 0, "downloaded": 0, "deduped": 0, "normalized": 0,
            "passed": 0, "rejected": 0, "failed": 0, "skipped": 0,
        }
        errors: list[dict[str, Any]] = []
        inserted_ids: list[int] = []
        items = list(items or [])
        stats["total"] = len(items)

        for idx, raw in enumerate(items):
            item = self._prepare_item(raw, idx, source_platform)
            if item is None:
                stats["failed"] += 1
                errors.append(
                    {
                        "item_key": f"item-{idx}", "stage": "prepare",
                        "error_code": UNEXPECTED, "message": "条目非 dict，无法处理",
                    }
                )
                continue
            key = item["item_key"]
            try:
                self._process_item(item, stats, errors, inserted_ids)
            except Exception as exc:  # 兜底：未分类异常不抛出（错误分类 UNEXPECTED，宪法第 8 节）
                stats["failed"] += 1
                errors.append(
                    {
                        "item_key": key, "stage": "pipeline", "error_code": UNEXPECTED,
                        "message": _truncate(f"{exc.__class__.__name__}: {exc}"),
                    }
                )
                log.exception("流水线条目未分类异常 item_key=%s", key)

        env = {
            "ffmpeg": "available" if detect_ffmpeg() else "pending",
            "downloader": "present" if self.components.get("download_service") else "missing",
            "dedup": "present" if self.components.get("dedup_service") else "missing",
            "normalizer": "present" if self.components.get("normalizer") else "missing",
            "tagger": "present" if self.components.get("tagger") else "missing",
            "compliance": "present" if self.components.get("compliance") else "missing",
        }
        return {
            "source_platform": source_platform,
            "mode": mode,
            "stats": stats,
            "errors": errors,
            "env": env,
            "inserted_ids": inserted_ids,
        }

    # ---------------------------------------------------------- 条目处理
    def _process_item(
        self, item: dict[str, Any], stats: dict[str, int], errors: list[dict[str, Any]], inserted_ids: list[int]
    ) -> str:
        """单条目流水线；返回终态：deduped/passed/rejected/failed/skipped（终态互斥）。"""
        key = item["item_key"]

        # ① 必填校验（context 1.1：source_platform/source_url 必填；asset_type 枚举）
        missing = [f for f in ("source_url", "source_platform") if not str(item.get(f) or "").strip()]
        if item.get("asset_type") not in ("video", "image"):
            missing.append("asset_type")
        if missing:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "prepare", "error_code": UNEXPECTED,
                    "message": f"缺少必填字段: {', '.join(missing)}",
                }
            )
            return "failed"

        # ② 去重预检（MD5 精确判重；R-M2-11 入库前必查）
        dedup = self.components.get("dedup_service")
        if dedup is None:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "dedup", "error_code": UNEXPECTED,
                    "message": "dedup_service 组件缺失，未做去重预检（defer 等待组件就绪）",
                }
            )
            return "skipped"
        check = None
        try:
            check = self._dedup_check(dedup, item, None)
        except FFmpegNotFoundError:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "dedup", "error_code": UNEXPECTED,
                    "message": "ffmpeg 未安装，无法计算视频关键帧 phash（环境待确认，defer）",
                }
            )
            return "skipped"
        except Exception as exc:  # 预检异常不阻断主流程（终态由 create_asset 认领兜底）
            errors.append(
                {
                    "item_key": key, "stage": "dedup", "error_code": UNEXPECTED,
                    "message": _truncate(f"去重预检异常: {exc}"),
                }
            )
            check = None
        if check is not None and check.get("is_duplicate"):
            stats["deduped"] += 1
            log.info("去重预检命中：item_key=%s reason=%s", key, check.get("reason"))
            return "deduped"

        # ③ 下载（组件缺失或下载失败 → failed 分类，任务书口径）
        downloader = self.components.get("download_service")
        if downloader is None:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "download", "error_code": UNEXPECTED,
                    "message": "download_service 组件缺失（未注入下载器）",
                }
            )
            return "failed"
        try:
            dl = downloader.download(item)
        except Exception as exc:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "download", "error_code": UNEXPECTED,
                    "message": _truncate(
                        f"下载异常: {exc} url={redact_url(str(item.get('source_url', '')))}"
                    ),
                }
            )
            return "failed"
        if not isinstance(dl, dict) or not dl.get("ok"):
            code = (dl or {}).get("error_code") or UNEXPECTED
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "download", "error_code": code,
                    "message": _truncate(
                        f"下载失败[{code}]: {(dl or {}).get('message') or ''} "
                        f"url={redact_url(str(item.get('source_url', '')))}"
                    ),
                }
            )
            return "failed"
        stats["downloaded"] += 1
        file_path = str(dl.get("file_path") or item.get("file_path") or "")
        item["file_path"] = file_path
        if dl.get("md5"):
            item["md5"] = str(dl["md5"])
        if dl.get("size") is not None:
            item["size"] = int(dl["size"])

        # ④ 去重复检（有本地文件时 MD5+phash 全量检查）
        has_file = bool(file_path) and Path(file_path).exists()
        if has_file:
            try:
                check = self._dedup_check(dedup, item, file_path)
            except FFmpegNotFoundError:
                stats["skipped"] += 1
                errors.append(
                    {
                        "item_key": key, "stage": "dedup", "error_code": UNEXPECTED,
                        "message": "ffmpeg 未安装，去重复检无法抽帧（环境待确认，defer）",
                    }
                )
                return "skipped"
            except Exception as exc:
                errors.append(
                    {
                        "item_key": key, "stage": "dedup", "error_code": UNEXPECTED,
                        "message": _truncate(f"去重复检异常: {exc}"),
                    }
                )
                check = None
            if check is not None and check.get("is_duplicate"):
                stats["deduped"] += 1
                return "deduped"

        # ⑤ 标准化（组件缺失/ffmpeg 缺失 → skipped；硬规格不达标 → rejected；双校验 R-M2-12）
        normalizer = self.components.get("normalizer")
        if normalizer is None:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "normalize", "error_code": UNEXPECTED,
                    "message": "normalizer 组件缺失（ffmpeg 标准化未就绪，defer）",
                }
            )
            return "skipped"
        try:
            validate_result = normalizer.validate(file_path or "")
            if not validate_result.get("passed"):
                stats["rejected"] += 1
                errors.append(
                    {
                        "item_key": key, "stage": "normalize", "error_code": PLATFORM_REJECT,
                        "message": _truncate(f"硬规格不达标: {self._failures_text(validate_result.get('failures'))}"),
                    }
                )
                return "rejected"
            stats["normalized"] += 1
            if has_file:
                out = normalizer.normalize(file_path, output_path=self._normalized_output(item, file_path))
                if not out.get("passed"):
                    stats["rejected"] += 1
                    errors.append(
                        {
                            "item_key": key, "stage": "normalize", "error_code": PLATFORM_REJECT,
                            "message": _truncate(f"转码后复检不达标: {self._failures_text(out.get('failures'))}"),
                        }
                    )
                    return "rejected"
                item["file_path"] = str(out.get("output_path") or item["file_path"])
        except NormalizerError as exc:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "normalize", "error_code": UNEXPECTED,
                    "message": _truncate(f"标准化不可用: {exc}（ffmpeg 环境待确认，defer）"),
                }
            )
            return "skipped"
        except Exception as exc:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "normalize", "error_code": UNEXPECTED,
                    "message": _truncate(f"标准化异常: {exc}"),
                }
            )
            return "failed"

        # ⑥ 标签（组件缺失 → 跳过该阶段继续；tags_json 可空）
        tags = None
        tagger = self.components.get("tagger")
        if tagger is not None:
            try:
                tags = self._normalize_tags(self._call_tagger(tagger, item))
            except TypeError:
                stats["skipped"] += 1
                errors.append(
                    {
                        "item_key": key, "stage": "tags", "error_code": UNEXPECTED,
                        "message": "tagger 组件接口不兼容（generate_tags 签名探测失败，defer）",
                    }
                )
                return "skipped"
            except Exception as exc:
                stats["failed"] += 1
                errors.append(
                    {
                        "item_key": key, "stage": "tags", "error_code": UNEXPECTED,
                        "message": _truncate(f"标签生成异常: {exc}"),
                    }
                )
                return "failed"

        # ⑦ 合规预审（缺失 → skipped 不入终态；reject → rejected 不入终态；pass → 终态入库）
        compliance = self.components.get("compliance")
        if compliance is None:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "compliance", "error_code": UNEXPECTED,
                    "message": "compliance 组件缺失（合规预审未就绪，不入终态，defer）",
                }
            )
            return "skipped"
        try:
            cresult = self._compliance_gate(compliance, item, tags)
        except TypeError:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "compliance", "error_code": UNEXPECTED,
                    "message": "compliance 组件接口不兼容（预审探测失败，B4-1 未就绪？defer）",
                }
            )
            return "skipped"
        except Exception as exc:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "compliance", "error_code": UNEXPECTED,
                    "message": _truncate(f"合规预审异常: {exc}"),
                }
            )
            return "failed"
        cresult = cresult or {}
        result = str(cresult.get("result") or "").lower()
        if result == "reject":
            stats["rejected"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "compliance", "error_code": PLATFORM_REJECT,
                    "message": _truncate(f"合规预审拒绝（R-M2-19）: {self._reject_reason(cresult)}"),
                }
            )
            return "rejected"
        if result != "pass":
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "compliance", "error_code": UNEXPECTED,
                    "message": f"合规预审结果未通过（result={result or '未知'}，defer）",
                }
            )
            return "skipped"

        # ⑧ 终态入库（repo.create_asset 指纹认领防并发；DuplicateAssetError → deduped）
        md5 = self._resolve_md5(item, file_path)
        if not md5:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "insert", "error_code": UNEXPECTED,
                    "message": "无法确定文件 MD5（下载结果/条目/本地文件均缺失）",
                }
            )
            return "failed"
        phash, phash_note = self._resolve_phash(item, file_path)
        if not phash:
            stats["skipped"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "insert", "error_code": UNEXPECTED,
                    "message": _truncate(phash_note or "无法确定 phash（defer）"),
                }
            )
            return "skipped"
        size = self._resolve_size(item, file_path)
        try:
            asset_id = self.repo.create_asset(
                asset_type=item["asset_type"],
                source_platform=item["source_platform"],
                source_url=item["source_url"],
                md5=md5,
                phash=phash,
                file_path=str(item.get("file_path") or file_path or ""),
                size=size,
                source_author=item.get("source_author"),
                duration=self._to_int(item.get("duration")),
                resolution=item.get("resolution"),
                tags_json=json.dumps(tags, ensure_ascii=False) if tags else None,
                heat_score=self._to_float(item.get("heat_score")),
                compliance_status="passed",
                derivation_note=item.get("derivation_note") or self._default_derivation(item["asset_type"]),
            )
        except DuplicateAssetError:
            stats["deduped"] += 1
            log.info("终态入库指纹冲突：item_key=%s（create_asset 认领兜底）", key)
            return "deduped"
        except Exception as exc:
            stats["failed"] += 1
            errors.append(
                {
                    "item_key": key, "stage": "insert", "error_code": UNEXPECTED,
                    "message": _truncate(f"入库异常: {exc}"),
                }
            )
            return "failed"
        stats["passed"] += 1
        inserted_ids.append(asset_id)
        log.info("素材入库：item_key=%s asset_id=%s md5=%s", key, asset_id, md5)

        # ⑧b 合规证据留痕（B4-1 evaluate_and_record → asset_compliance_checks 审计；
        #    失败不影响已入库终态，仅记录错误）
        self._record_compliance_evidence(compliance, asset_id, item, tags, errors, key)

        # ⑨ 上传（可选，入库后；失败不影响已入库终态，R-M2-23 状态机由 M3 侧驱动）
        upload = self.components.get("upload")
        if upload is not None:
            try:
                upload.upload(asset_id=asset_id, item=item)
            except TypeError:
                try:
                    upload.upload(asset_id)
                except Exception as exc:
                    errors.append(
                        {
                            "item_key": key, "stage": "upload", "error_code": UNEXPECTED,
                            "message": _truncate(f"上传回调异常（不影响入库）: {exc}"),
                        }
                    )
            except Exception as exc:
                errors.append(
                    {
                        "item_key": key, "stage": "upload", "error_code": UNEXPECTED,
                        "message": _truncate(f"上传回调异常（不影响入库）: {exc}"),
                    }
                )
        return "passed"

    # ---------------------------------------------------------- 内部工具
    @staticmethod
    def _prepare_item(raw: Any, idx: int, source_platform: str) -> Optional[dict[str, Any]]:
        """条目归一：非 dict → None；补齐默认字段与 item_key（幂等，不改原输入）。"""
        if not isinstance(raw, dict):
            return None
        item = dict(raw)
        item.setdefault("asset_type", "video")
        item.setdefault("source_platform", source_platform)
        item.setdefault("source_url", "")
        item["item_key"] = str(
            item.get("item_key") or item.get("video_id") or item.get("source_url") or f"item-{idx}"
        )
        return item

    @staticmethod
    def _dedup_check(svc: Any, item: dict[str, Any], file_path: Optional[str]) -> Optional[dict[str, Any]]:
        """DedupService 检查：有本地文件 → 全量（MD5+phash）；否则 32 位 md5 精确预检。

        视频抽帧需 ffmpeg（FFmpegFrameExtractor 缺失抛 FFmpegNotFoundError，由调用方处理）。
        """
        asset_type = item.get("asset_type") or "video"
        path = str(file_path or "")
        if path and Path(path).exists():
            fn = svc.check_video if asset_type == "video" else svc.check_image
            return fn(path)
        md5 = str(item.get("md5") or "").strip()
        if md5:
            fn = svc.check_video if asset_type == "video" else svc.check_image
            return fn(md5)
        return None

    @staticmethod
    def _resolve_md5(item: dict[str, Any], file_path: str) -> str:
        md5 = str(item.get("md5") or "").strip()
        if md5:
            return md5
        path = str(file_path or "")
        if path and Path(path).exists():
            from .dedup import compute_md5

            try:
                return compute_md5(path)
            except OSError:
                return ""
        return ""

    @staticmethod
    def _resolve_phash(item: dict[str, Any], file_path: str) -> tuple[str, Optional[str]]:
        """phash 解析：条目自带 > 本地文件计算（图片整图 / 视频关键帧 JSON）。

        视频 phash 需 ffmpeg 抽帧（R-M2-15 缺失不静默，返回待确认提示由调用方 defer）。
        """
        phash = str(item.get("phash") or "").strip()
        if phash:
            return phash, None
        path = str(file_path or "")
        asset_type = item.get("asset_type") or "video"
        if path and Path(path).exists():
            try:
                if asset_type == "image":
                    from .dedup import image_phash

                    return image_phash(path), None
                from .dedup import video_phash

                return video_phash(path)["combined"], None
            except FFmpegNotFoundError as exc:
                return None, f"视频 phash 需 ffmpeg 抽帧（环境待确认）: {str(exc)[:120]}"
            except Exception as exc:
                return None, f"phash 计算失败: {str(exc)[:120]}"
        return None, "无 phash 且无本地文件（视频需 ffmpeg 抽帧，环境待确认；defer）"

    @staticmethod
    def _resolve_size(item: dict[str, Any], file_path: str) -> int:
        size = item.get("size")
        if size is not None:
            try:
                return int(size)
            except (TypeError, ValueError):
                pass
        path = str(file_path or "")
        if path and Path(path).exists():
            try:
                return int(Path(path).stat().st_size)
            except OSError:
                pass
        return 0

    def _normalized_output(self, item: dict[str, Any], file_path: str) -> str:
        fmt = self.config.normalize.output_format
        p = Path(file_path)
        return str(p.with_name(p.stem + ".normalized." + fmt))

    def _call_tagger(self, tagger: Any, item: dict[str, Any]) -> Any:
        """标签组件防御式调用：B4-1 模块函数协议 → 通用实例协议，逐级探测。

        B4-1 真实协议：generate_tags(source_platform, source_author, title,
        category_hint, max_tags, config)；通用协议：generate_tags(item)。
        签名全不兼容抛 TypeError（调用方按组件未就绪降级）。
        """
        attempts = (
            lambda: tagger(
                source_platform=item.get("source_platform"),
                source_author=item.get("source_author"),
                title=item.get("title"),
                category_hint=item.get("category_hint"),
                config=self.config,
            ),
            lambda: tagger(
                source_platform=item.get("source_platform"),
                source_author=item.get("source_author"),
                title=item.get("title"),
            ),
            lambda: tagger.generate_tags(item=item),
            lambda: tagger.generate_tags(item),
        )
        last: Optional[BaseException] = None
        for fn in attempts:
            try:
                return fn()
            except (TypeError, AttributeError) as exc:
                last = exc
        raise last  # type: ignore[misc]

    @staticmethod
    def _normalize_tags(raw: Any) -> list[str]:
        """标签结果归一：list → 字符串列表；dict（{"tags": [...]}）→ 取 tags；其余 → []。"""
        if isinstance(raw, dict):
            raw = raw.get("tags") or raw.get("tags_json") or []
        if not isinstance(raw, (list, tuple)):
            return []
        return [str(t) for t in raw if str(t).strip()]

    def _compliance_gate(self, compliance: Any, item: dict[str, Any], tags: Optional[list[str]]) -> dict[str, Any]:
        """合规预审门（入库前）：B4-1 check_material 优先 → 通用 evaluate_and_record 兜底。

        返回 {"result": "pass"|"reject"|"review", ...}；签名全不兼容抛 TypeError。
        """
        title = str(item.get("title") or "")
        extra = self._compliance_extra_text(item, tags)
        attempts = (
            lambda: compliance.check_material(
                title=title, extra_text=extra, asset_type=item.get("asset_type")
            ),
            lambda: compliance.check_material(title=title, extra_text=extra),
            lambda: compliance.evaluate_and_record(item=item, tags=tags),
            lambda: compliance.evaluate_and_record(item, tags),
            lambda: compliance.evaluate_and_record(item),
        )
        last: Optional[BaseException] = None
        for fn in attempts:
            try:
                return fn()
            except (TypeError, AttributeError) as exc:
                last = exc
        raise last  # type: ignore[misc]

    def _record_compliance_evidence(
        self,
        compliance: Any,
        asset_id: int,
        item: dict[str, Any],
        tags: Optional[list[str]],
        errors: list[dict[str, Any]],
        key: str,
    ) -> None:
        """入库后合规证据留痕（B4-1 evaluate_and_record → repo.record_compliance_check）。

        任何失败只记错误条目，不影响已入库终态（幂等可补录）。
        """
        title = str(item.get("title") or "")
        extra = self._compliance_extra_text(item, tags)
        note = item.get("derivation_note")
        platform = item.get("source_platform")
        attempts = (
            lambda: compliance.evaluate_and_record(
                repo=self.repo, asset_id=asset_id, title=title, extra_text=extra,
                derivation_note=note, source_platform=platform,
            ),
            lambda: compliance.evaluate_and_record(
                self.repo, asset_id, title=title, extra_text=extra
            ),
            lambda: compliance.evaluate_and_record(asset_id=asset_id, item=item),
            lambda: compliance.evaluate_and_record(asset_id=asset_id),
        )
        last: Optional[BaseException] = None
        for fn in attempts:
            try:
                fn()
                return
            except (TypeError, AttributeError) as exc:
                last = exc
                continue
            except Exception as exc:
                errors.append(
                    {
                        "item_key": key, "stage": "compliance_evidence", "error_code": UNEXPECTED,
                        "message": _truncate(f"合规证据留痕异常（不影响入库）: {exc}"),
                    }
                )
                return
        errors.append(
            {
                "item_key": key, "stage": "compliance_evidence", "error_code": UNEXPECTED,
                "message": f"合规证据留痕接口不兼容（{last}）",
            }
        )

    @staticmethod
    def _compliance_extra_text(item: dict[str, Any], tags: Optional[list[str]]) -> str:
        """合规预审附加文本：标签 + 达人昵称（供应链词/品牌词/功效词全字段覆盖，R-M2-19）。"""
        parts = [str(t) for t in (tags or []) if str(t).strip()]
        author = str(item.get("source_author") or "").strip()
        if author:
            parts.append(author)
        return " ".join(parts)

    @staticmethod
    def _reject_reason(cresult: dict[str, Any]) -> str:
        """合规拒绝理由：reasons（B4-1）优先 → 命中词扁平化（dict/list/str 兼容）兜底。"""
        reasons = cresult.get("reasons")
        if isinstance(reasons, list) and reasons:
            return "; ".join(str(r) for r in reasons[:3])
        words = cresult.get("hit_words") or cresult.get("hit_words_json") or []
        if isinstance(words, dict):
            words = [w for ws in words.values() if isinstance(ws, list) for w in ws]
        if isinstance(words, str):
            words = [words]
        words = [str(w) for w in words if str(w).strip()][:3]
        return f"命中词: {', '.join(words)}" if words else "（未提供命中词）"

    @staticmethod
    def _failures_text(failures: Any) -> str:
        if not failures:
            return "（无明细）"
        parts = [
            f"{f.get('field')}: {f.get('reason')}"
            for f in failures[:5]
            if isinstance(f, dict) and f.get("reason")
        ]
        return "; ".join(parts) if parts else "（无明细）"

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _default_derivation(asset_type: str) -> str:
        """二创义务标记默认值（R-M2-18：入库强制标记来源与二创义务）。"""
        if asset_type == "video":
            return "去水印/混剪/换文案（二创义务，R-M2-18）"
        return "同款图参考（二创义务，R-M2-18）"

    # ---------------------------------------------------------- 日采集量统计
    def daily_stats(self, db: Any = None, date_str: Optional[str] = None) -> dict[str, Any]:
        """日采集量统计：按 source_platform/asset_type/upload_status 聚合
        asset_items.created_at 当日数据（ISO8601 UTC 取 YYYY-MM-DD 日期）。

        空库/查询失败返回全零结构不崩（支撑「日采集量可观测」验收）。
        """
        db = db or self.db
        if db is None:
            return self._empty_daily_stats(date_str)
        from . import tables as T

        try:
            with db.session() as s:
                rows = s.execute(
                    select(
                        T.AssetItem.created_at,
                        T.AssetItem.source_platform,
                        T.AssetItem.asset_type,
                        T.AssetItem.upload_status,
                    )
                ).all()
        except Exception as exc:
            log.warning("daily_stats 查询失败（按空结构返回）: %s", exc)
            return self._empty_daily_stats(date_str)

        total = 0
        by_platform: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        granular: dict[tuple[str, str, str, str], int] = {}
        for created_at, platform, asset_type, upload_status in rows:
            day = str(created_at or "")[:10]
            if date_str and day != date_str:
                continue
            total += 1
            pk, tk, sk = (
                str(platform or "unknown"),
                str(asset_type or "unknown"),
                str(upload_status or "unknown"),
            )
            by_platform[pk] = by_platform.get(pk, 0) + 1
            by_type[tk] = by_type.get(tk, 0) + 1
            by_status[sk] = by_status.get(sk, 0) + 1
            granular[(day, pk, tk, sk)] = granular.get((day, pk, tk, sk), 0) + 1

        return {
            "date": date_str,
            "total": total,
            "by_source_platform": by_platform,
            "by_asset_type": by_type,
            "by_upload_status": by_status,
            "granular": [
                {"date": d, "source_platform": p, "asset_type": t, "upload_status": st, "count": c}
                for (d, p, t, st), c in sorted(granular.items())
            ],
        }

    @staticmethod
    def _empty_daily_stats(date_str: Optional[str]) -> dict[str, Any]:
        return {
            "date": date_str,
            "total": 0,
            "by_source_platform": {},
            "by_asset_type": {},
            "by_upload_status": {},
            "granular": [],
        }
