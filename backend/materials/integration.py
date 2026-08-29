"""M2 自动收集素材模块 · 数据联动服务层（子代理 B4-2 + 相关性门 C3 v1.1）。

三部分交付（对齐 context/README.md 3.3「与 M5 投放联动（双向）」契约 +
迁移清单 REC-迁移-03 C3 相关性门）：

1. **evaluation 评估标签回流协议对接**（M5→M2）：
   `EvaluationFeedbackService.receive_evaluation` —— 校验枚举（非法→PLATFORM_REJECT）、
   素材不存在→NO_MATCH、合法→`repo.update_evaluation`（写 asset_evaluations 审计 +
   更新 asset_items.evaluation），结构化返回不抛异常；`get_evaluation` 读当前标签。
   M2 不主动写 evaluation，仅 M5 回写（context 1.4）。

2. **上传小店素材库接口抽象**（M2 侧抽象承担；context 3.3 M2→M5 绑定前提）：
   - `UploadProvider`（ABC）：`upload(...)` 返回 platform_material_id、`health()` 状态；
   - `MockUploadProvider`：fixtures/测试用（可配置成功/失败/重复）；
   - `ShopMaterialUploadProvider`：真实实现骨架（待小店素材库 API/登录态确认，
     方法抛 NotImplementedError，**不写死凭据/接口地址**，P-004）；
   - `MaterialUploadService`：幂等编排（已上传直接返回 → provider.upload →
     `repo.mark_uploaded` 回填 + asset_uploads 记录；失败按全局码表分类返回，不抛出）。

3. **相关性门预检接口**（M3→M2，REC-迁移-03 C3）：
   `RelevanceGateService.receive_relevance` —— 消费 M3 relevance 判定结果
   （result: pass/reject/manual_review）落 `asset_items.relevance_status`
   （passed/failed/manual_review，枚举唯一口径见 config.RELEVANCE_STATUS_VALUES）；
   非法枚举→PLATFORM_REJECT、素材不存在→NO_MATCH、合法→幂等回写；
   `get_relevance_status` 读当前状态、`is_ready_for_chain` 判定是否可进入询价/上架链
   （仅 relevance_status=passed 放行；failed 淘汰、manual_review 待人工确认目标款）。

错误分类复用全局码表（VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/
NO_MATCH/PLATFORM_REJECT/UNEXPECTED）；服务层任何异常不向上抛出（对齐 R-M2-09
「本类任何异常不抛出」纪律）。
密钥纪律（P-004）：本文件无任何明文凭据/接口地址，仅引用环境变量名
（MATERIALS_UPLOAD_MODE / MATERIALS_UPLOAD_PROVIDER_PARAMS，见 config.upload）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from .config import (
    EVALUATION_VALUES,  # 与 config.py 同口径（唯一枚举源）
    RELEVANCE_RESULT_TO_STATUS,
    RELEVANCE_STATUS_VALUES,
)
from .repo import AssetNotFoundError, AssetRepo, DuplicateUploadError

logger = logging.getLogger(__name__)

__all__ = [
    "EVALUATION_VALUES",
    "EvaluationFeedbackService",
    "UploadProvider",
    "UploadError",
    "UploadTimeoutError",
    "UploadRejectedError",
    "MockUploadProvider",
    "ShopMaterialUploadProvider",
    "MaterialUploadService",
    "build_upload_provider",
    # 相关性门（REC-迁移-03 C3）
    "RELEVANCE_STATUS_VALUES",
    "RELEVANCE_RESULT_TO_STATUS",
    "RelevanceGateService",
]


# ===========================================================================
# 一、evaluation 评估标签回流协议（M5→M2，context 1.4 / 3.3）
# ===========================================================================
class EvaluationFeedbackService:
    """M5 评估标签回流协议对接（幂等审计）。

    协议：
    - evaluation 非法枚举 → `{ok: False, code: "PLATFORM_REJECT", ...}`（拒绝，不落库）；
    - 素材不存在 → `{ok: False, code: "NO_MATCH", ...}`；
    - 合法 → `repo.update_evaluation`（写 asset_evaluations 审计 + 更新
      asset_items.evaluation，幂等按 repo 语义：重复回写同值收敛不报错，
      审计表为台账每次回写留痕）→ `{ok, asset_id, evaluation, recorded}`。

    失败一律结构化返回，本服务不抛异常。
    """

    def __init__(self, repo: AssetRepo):
        self.repo = repo

    def receive_evaluation(
        self,
        asset_id: int,
        evaluation: str,
        evidence: Any = None,
        source_agent: str = "M5",
    ) -> dict[str, Any]:
        """接收 M5 评估标签回写（幂等审计）。evidence 为回流批次/报表快照摘要。"""
        if evaluation not in EVALUATION_VALUES:
            return {
                "ok": False,
                "code": "PLATFORM_REJECT",
                "reason": (
                    f"invalid evaluation {evaluation!r}; allowed values: "
                    f"{', '.join(EVALUATION_VALUES)}"
                ),
                "asset_id": asset_id,
            }
        if self.repo.get_asset(asset_id) is None:
            return {
                "ok": False,
                "code": "NO_MATCH",
                "reason": f"asset {asset_id} not found",
                "asset_id": asset_id,
            }
        try:
            self.repo.update_evaluation(
                asset_id,
                evaluation,
                evidence_json=evidence,
                source_agent=source_agent,
            )
        except AssetNotFoundError:
            # 校验与写入之间的并发删除兜底：仍按 NO_MATCH 结构化返回（不抛出）
            return {
                "ok": False,
                "code": "NO_MATCH",
                "reason": f"asset {asset_id} not found",
                "asset_id": asset_id,
            }
        return {
            "ok": True,
            "asset_id": asset_id,
            "evaluation": evaluation,
            "recorded": True,  # 本次调用已写 asset_evaluations 审计（repo 台账语义）
        }

    def get_evaluation(self, asset_id: int) -> str | None:
        """读当前评估标签；素材不存在返回 None。"""
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            return None
        return asset.get("evaluation")


# ===========================================================================
# 一·B、相关性门预检接口（M3→M2，REC-迁移-03 C3；契约见 data-audit DA-010）
# ===========================================================================
class RelevanceGateService:
    """M2 相关性门预检接口：消费 M3 relevance 判定结果（幂等，结构化返回）。

    协议（对齐迁移清单 C3 + data-exchange/m2-m3-m4-relevance-gate.json）：
    - `receive_relevance(asset_id, result)`：result 为 M3 RelevanceGate 落库口径
      **pass / reject / manual_review**（opt_review_records.result），映射到
      asset_items.relevance_status：passed / failed / manual_review
      （枚举唯一口径 config.RELEVANCE_STATUS_VALUES，映射 RELEVANCE_RESULT_TO_STATUS）；
    - 非法 result → `{ok: False, code: "PLATFORM_REJECT", ...}`（拒绝，不落库）；
    - 素材不存在 → `{ok: False, code: "NO_MATCH", ...}`；
    - 合法 → `repo.update_relevance_status`（幂等收敛，不抛异常）
      → `{ok, asset_id, relevance_status, changed}`（changed=本次是否发生状态变化）；
    - `is_ready_for_chain(asset_id)`：**仅 relevance_status=passed 放行**进入询价/上架链
      （failed 淘汰、manual_review 待人工确认目标款、pending 未判定——均不放行）；
    - `get_relevance_status(asset_id)`：读当前状态，素材不存在返回 None。
    """

    def __init__(self, repo: AssetRepo):
        self.repo = repo

    def receive_relevance(
        self,
        asset_id: int,
        result: str,
        evidence: Any = None,
        source_agent: str = "M3",
    ) -> dict[str, Any]:
        """接收 M3 relevance 判定结果（幂等回写 relevance_status）。

        evidence 为 M3 判定证据摘要（verdict/style_count/review_id 等，脱敏后）。
        """
        if result not in RELEVANCE_RESULT_TO_STATUS:
            return {
                "ok": False,
                "code": "PLATFORM_REJECT",
                "reason": (
                    f"invalid relevance result {result!r}; allowed values: "
                    f"{', '.join(sorted(RELEVANCE_RESULT_TO_STATUS))}"
                    "（M3 gate.result 口径：pass/reject/manual_review）"
                ),
                "asset_id": asset_id,
            }
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            return {
                "ok": False,
                "code": "NO_MATCH",
                "reason": f"asset {asset_id} not found",
                "asset_id": asset_id,
            }
        status = RELEVANCE_RESULT_TO_STATUS[result]
        old = asset.get("relevance_status")
        try:
            self.repo.update_relevance_status(asset_id, status)
        except AssetNotFoundError:
            # 校验与写入之间的并发删除兜底：仍按 NO_MATCH 结构化返回（不抛出）
            return {
                "ok": False,
                "code": "NO_MATCH",
                "reason": f"asset {asset_id} not found",
                "asset_id": asset_id,
            }
        if evidence is not None:
            logger.info(
                "relevance updated asset_id=%s result=%s status=%s source=%s",
                asset_id, result, status, source_agent,
            )
        return {
            "ok": True,
            "asset_id": asset_id,
            "relevance_status": status,
            "changed": old != status,  # 幂等：同值重复回写 changed=False
        }

    def get_relevance_status(self, asset_id: int) -> str | None:
        """读当前相关性门状态；素材不存在返回 None。"""
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            return None
        return asset.get("relevance_status")

    def is_ready_for_chain(self, asset_id: int) -> bool:
        """是否可进入询价/上架链：仅 relevance_status=passed 放行（REC-迁移-03 C3）。

        failed（不相关淘汰）/ manual_review（多款式待人工确认目标款）/
        pending（未判定）均不放行；素材不存在返回 False。
        """
        return self.get_relevance_status(asset_id) == "passed"


# ===========================================================================
# 二、上传小店素材库接口抽象（context 3.3；待小店素材库 API/登录态确认）
# ===========================================================================
class UploadError(Exception):
    """上传失败基类（服务层按 error_code 分类结构化返回，不向上抛出）。"""

    def __init__(
        self,
        error_code: str,
        message: str = "",
        *,
        evidence: Any = None,
    ):
        self.error_code = error_code
        self.message = message
        self.evidence = evidence
        super().__init__(f"[{error_code}] {message}")


class UploadTimeoutError(UploadError):
    """上传超时 → TIMEOUT（对齐全局码表，R-M2-06）。"""

    def __init__(self, message: str = "upload timeout", evidence: Any = None):
        super().__init__("TIMEOUT", message, evidence=evidence)


class UploadRejectedError(UploadError):
    """平台拒绝/参数错误 → PLATFORM_REJECT（记录证据，人工核查）。"""

    def __init__(
        self, message: str = "platform rejected upload", evidence: Any = None
    ):
        super().__init__("PLATFORM_REJECT", message, evidence=evidence)


class UploadProvider(ABC):
    """小店素材库上传 provider 抽象。

    实现约定：
    - `upload(asset_id, file_path, title, metadata) -> str` 返回 platform_material_id
      （小店素材库 ID，供 M5 投放绑定；唯一约束防重复上传）；
    - 失败必须抛 `UploadError`（带 error_code 分类）或由服务层按异常类型兜底分类；
    - **不写死凭据/接口地址**（P-004），一律读 config.upload 环境变量；
    - `health()` 返回结构化状态 `{ok, mode, detail?}`。
    """

    @abstractmethod
    def upload(
        self,
        asset_id: int,
        file_path: str,
        title: str,
        metadata: dict[str, Any],
    ) -> str:
        """上传素材到小店素材库，返回 platform_material_id。"""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """健康检查（结构化 dict）。"""


class MockUploadProvider(UploadProvider):
    """fixtures/测试用上传 provider（零外网零登录态，R-M2-17）。

    构造参数：
    - `fail_code`：None=成功（默认）；"TIMEOUT"/"PLATFORM_REJECT"/"UNEXPECTED" 或任意
      全局错误码 → 上传抛对应 `UploadError`（UNEXPECTED 抛普通 RuntimeError 模拟
      未预期异常，由服务层兜底分类）；
    - `material_id`：成功时返回的 platform_material_id（默认 `mock-mat-{asset_id}`）；
      固定传同一值可模拟「重复/冲突」（配合服务层 DuplicateUploadError 分类）。
    同 asset_id 重复上传返回同一 material_id（幂等语义在服务层）。
    """

    def __init__(
        self,
        fail_code: str | None = None,
        material_id: str | None = None,
    ):
        self.fail_code = fail_code
        self.material_id = material_id
        self.calls: list[dict[str, Any]] = []

    def upload(
        self,
        asset_id: int,
        file_path: str,
        title: str,
        metadata: dict[str, Any],
    ) -> str:
        self.calls.append(
            {
                "asset_id": asset_id,
                "file_path": file_path,
                "title": title,
                "metadata": metadata,
            }
        )
        if self.fail_code == "TIMEOUT":
            raise UploadTimeoutError(evidence={"mock": True})
        if self.fail_code == "PLATFORM_REJECT":
            raise UploadRejectedError(evidence={"mock_reason": "fixtures reject"})
        if self.fail_code == "UNEXPECTED":
            raise RuntimeError("mock unexpected failure")  # 服务层兜底 → UNEXPECTED
        if self.fail_code:
            raise UploadError(self.fail_code, f"mock fail: {self.fail_code}")
        return self.material_id or f"mock-mat-{asset_id}"

    def health(self) -> dict[str, Any]:
        return {"ok": self.fail_code is None, "mode": "mock", "calls": len(self.calls)}


class ShopMaterialUploadProvider(UploadProvider):
    """真实小店素材库上传 provider **骨架**（待小店素材库 API/登录态确认）。

    当前状态：
    - 构造读 `config.upload`（`MATERIALS_UPLOAD_MODE` / `MATERIALS_UPLOAD_PROVIDER_PARAMS`），
      只读环境变量名/非敏感参数，**不写死凭据/接口地址**（P-004）；
    - `upload` / `health` 抛 NotImplementedError（骨架占位）。

    待 API/登录态确认后的切换步骤（见汇报）：
    1. 在 context/README.md 登记小店素材库 API 契约 + 环境变量清单（仅变量名）；
    2. 本类实现 `upload()`：登录态获取 → 上传文件 → 解析 platform_material_id →
       失败按全局码表抛 `UploadError`（TIMEOUT/PLATFORM_REJECT/AUTH_REQUIRED 等）；
    3. `config.upload.mode` 由 "mock" 切 "shop"，回归上传链路测试。
    """

    def __init__(self, config: Any = None):
        from .config import load_config  # 延迟导入避免循环

        self.config = config if config is not None else load_config().upload

    def upload(
        self,
        asset_id: int,
        file_path: str,
        title: str,
        metadata: dict[str, Any],
    ) -> str:
        raise NotImplementedError(
            "ShopMaterialUploadProvider.upload: 待小店素材库上传 API/登录态确认后实现"
            f"（config.upload.mode='shop'，mode={self.config.mode!r}；凭据仅走环境变量）"
        )

    def health(self) -> dict[str, Any]:
        raise NotImplementedError(
            "ShopMaterialUploadProvider.health: 待小店素材库 API/登录态确认后实现"
        )


class MaterialUploadService:
    """素材上传小店素材库编排（context 3.3：上传后回填 platform_material_id 供 M5 绑定）。

    流程（幂等、断点可重试）：
    1. 素材不存在 → `{ok: False, code: "NO_MATCH"}`（不调 provider）；
    2. `asset_items.platform_material_id` 已存在 → 直接返回「已上传」（不再调
       provider、不重复插 asset_uploads 记录）；
    3. `provider.upload(...)`（构造 title/metadata）→ 成功拿 platform_material_id；
    4. `repo.mark_uploaded`（回填 asset_items + 写 asset_uploads 记录）；
    5. 失败按异常分类（TIMEOUT/PLATFORM_REJECT/UNEXPECTED 等）结构化返回，**不抛出**；
       `platform_material_id` 被其他素材占用 → PLATFORM_REJECT（防重复回填）。

    注意：若 provider 已上传成功但 mark_uploaded 失败（如 ID 冲突），平台侧素材已存在，
    需人工核对后重试/复用该 ID（断点续跑原则：失败可重试，证据 JSON 留痕）。
    """

    def __init__(self, repo: AssetRepo, provider: UploadProvider):
        self.repo = repo
        self.provider = provider

    def upload(self, asset_id: int, *, title: str | None = None) -> dict[str, Any]:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            return {
                "ok": False,
                "code": "NO_MATCH",
                "reason": f"asset {asset_id} not found",
                "asset_id": asset_id,
            }
        if asset.get("platform_material_id"):
            # 幂等：已上传（含断点续跑场景），直接返回不重复上传
            return {
                "ok": True,
                "asset_id": asset_id,
                "platform_material_id": asset["platform_material_id"],
                "already_uploaded": True,
            }
        metadata = self._build_metadata(asset)
        try:
            material_id = self.provider.upload(
                asset_id=asset_id,
                file_path=asset["file_path"],
                title=title or self._default_title(asset),
                metadata=metadata,
            )
        except UploadError as exc:
            logger.warning("upload failed asset_id=%s code=%s", asset_id, exc.error_code)
            return self._fail(asset_id, exc.error_code, exc.message, exc.evidence)
        except Exception as exc:  # noqa: BLE001 —— 服务层吞异常，分类返回（R-M2-09 纪律）
            logger.warning("upload unexpected asset_id=%s type=%s", asset_id, type(exc).__name__)
            return self._fail(
                asset_id,
                "UNEXPECTED",
                f"unexpected upload failure: {type(exc).__name__}",
                None,
            )
        try:
            self.repo.mark_uploaded(asset_id, material_id)
        except DuplicateUploadError as exc:
            logger.warning("upload conflict asset_id=%s material_id=%s", asset_id, material_id)
            return self._fail(
                asset_id,
                "PLATFORM_REJECT",
                (
                    f"platform_material_id {material_id} already owned by "
                    f"asset {exc.owner_asset_id}"
                ),
                None,
            )
        except AssetNotFoundError:
            return self._fail(asset_id, "NO_MATCH", f"asset {asset_id} not found", None)
        logger.info("upload success asset_id=%s material_id=%s", asset_id, material_id)
        return {
            "ok": True,
            "asset_id": asset_id,
            "platform_material_id": material_id,
            "already_uploaded": False,
        }

    def health(self) -> dict[str, Any]:
        return self.provider.health()

    # ------------------------------------------------------------ 内部工具
    @staticmethod
    def _default_title(asset: dict[str, Any]) -> str:
        return f"素材-{asset['id']}"

    @staticmethod
    def _build_metadata(asset: dict[str, Any]) -> dict[str, Any]:
        """构造上传元数据（全部非敏感字段；不含任何凭据/路径外泄）。"""
        keys = (
            "asset_type",
            "source_platform",
            "source_author",
            "duration",
            "resolution",
            "size",
            "tags_json",
            "heat_score",
            "compliance_status",
            "derivation_note",
        )
        return {k: asset.get(k) for k in keys}

    @staticmethod
    def _fail(
        asset_id: int,
        code: str,
        reason: str,
        evidence: Any,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "code": code,
            "reason": reason,
            "evidence": evidence,
            "asset_id": asset_id,
        }


def build_upload_provider(config: Any = None) -> UploadProvider:
    """按 config.upload.mode 构造 provider：mock（默认，fixtures）/ shop（真实骨架）。

    mode 未知 → 抛 UploadError（UNEXPECTED）——配置错误显式暴露，不静默降级。
    """
    from .config import load_config  # 延迟导入避免循环

    cfg = config if config is not None else load_config()
    mode = cfg.upload.mode
    if mode == "shop":
        return ShopMaterialUploadProvider(cfg.upload)
    if mode == "mock":
        return MockUploadProvider()
    raise UploadError("UNEXPECTED", f"unknown upload mode: {mode!r}")
