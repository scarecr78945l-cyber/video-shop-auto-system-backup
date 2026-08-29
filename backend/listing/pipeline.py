"""M4 自动上架流水线编排（端到端模拟，零真实平台调用）。

- 构造注入：gate（P2 门禁）/ adapter（P1 微信 OpenAPI mock）/ repo（P3）/
  state_machine（P3，R22 断言）/ rejection（P4 拒审处理）/ link_verifier（可选，
  默认 mock 恒 True）——全部可替换，便于测试与离线模拟。
- 阶段流：gate 校验（失败不入队）→ 幂等 → 入队(pending) → creating → draft →
  platform_auditing → listed（R22 唯一判据）| rejected → retry_candidate | manual。
- R22：listed 唯一判据 = query_audit_status=通过 且 get_product_link 返回 且
  link_verifier(url) 为真；否则不迁移 listed，状态停留 platform_auditing。
- 断点续跑语义：全程异常 → 结构化失败 {ok, stage, error_code, evidence}，
  任务状态留在最近合法状态，不伪造状态（07 文档原则：失败不阻塞 OpenAPI 队列）。
- REC-融合 P0-1（decisions D14）：上架类目记忆接线——gate 前按类目预填
  logistics_template（required_fields 仅标记，C2 attrs_complete 由迁移子代理落地）；
  上架成功/拒审记录类目提交计数；类目拒审率 ≥50% 或连续图片拒审 ≥3 强制转人工。

运行：cd backend && python -m pytest tests/test_listing_pipeline.py -q --basetemp=".pytest-tmp-m4"
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable, Optional

from adapters.wechat_openapi import WechatApiError, WechatOpenApiAdapter
from services.listing_gate import ListingCandidate, ListingGate, PurchaseSettings

from .models import ListingTask
from .platform_rejection import RejectionHandler
from .repo import ListingRepo
from .state_machine import (
    IllegalTransitionError,
    ListedLinkVerificationError,
    ListingStateMachine,
)


class ListingPipeline:
    """上架流水线编排器：submit / requalify_and_resubmit 两个对外入口。"""

    def __init__(
        self,
        gate: ListingGate,
        adapter: WechatOpenApiAdapter,
        repo: ListingRepo,
        state_machine: ListingStateMachine,
        rejection: RejectionHandler,
        link_verifier: Optional[Callable[[str], bool]] = None,
    ):
        self.gate = gate
        self.adapter = adapter
        self.repo = repo
        self.state_machine = state_machine
        self.rejection = rejection
        # 链接可达性验证：默认 mock 恒 True（离线/模拟模式）
        self.link_verifier = link_verifier or (lambda url: True)

    # ------------------------------------------------------------ 提交入口

    def submit(
        self,
        candidate: ListingCandidate,
        generation_version: str = "",
    ) -> dict:
        """端到端上架：门禁 → 幂等 → 入队 → SPU/SKU/图 → 审核 → 上架/拒审分流。

        返回统一结构：
          - 门禁失败：{ok: False, stage: "gate", gate_result}（不入队）；
          - 幂等命中：{ok: True, existing: True, task_id, status}；
          - 成功：{ok: True, stage, task_id, product_link?, evidence}；
          - 失败：{ok: False, stage, error_code, evidence}（任务留在最近合法状态）。
        """
        # 0) REC-融合 P0-1：上架类目记忆预填（gate 前——预填字段参与门禁，
        #    缺运费模板的单不再因无记忆字段被拦；不覆盖显式值）
        candidate, prefill = self._prefill_from_category_memory(candidate)

        # 1) 门禁（P2）：六项硬门禁任一不过 → 不入队
        gate_result = self.gate.evaluate(candidate)
        if not gate_result.passed:
            return {
                "ok": False,
                "stage": "gate",
                "gate_result": gate_result.model_dump(),
                "category_memory": prefill,
            }

        # 2) 幂等：同 (product_id, generation_version) 已有任务 → 复用，不重复创建
        existing = self.repo.get_task_by_product(candidate.product_id, generation_version)
        if existing is not None:
            return {
                "ok": True,
                "existing": True,
                "task_id": existing.task_id,
                "status": existing.status,
                "category_memory": prefill,
            }

        # 3) 入队 + 状态链启动
        task = ListingTask(
            task_id=f"listing_{uuid.uuid4().hex[:12]}",
            product_id=candidate.product_id,
            generation_version=generation_version,
            stage="listing_upload",
            status="pending",
            gate_result=gate_result.model_dump(),
        )
        self.repo.create_task(task)
        if prefill:
            # 预填证据留痕（脱敏：仅预填字段名/值，无密钥）
            self.repo.append_op_log(
                task_id=task.task_id,
                api="category_memory_prefill",
                direction="prefill",
                payload_digest="",
                evidence_json=json.dumps(prefill, ensure_ascii=False),
            )
        task = self.state_machine.transition(task, "creating")

        return self._upload_and_audit(task, candidate, prefill)

    # ------------------------------------------------------------ 拒审重提入口

    def requalify_and_resubmit(
        self,
        task_id: str,
        candidate: ListingCandidate,
    ) -> dict:
        """拒审后重提：仅 retry_candidate 任务可重提（P4 二次门禁）。

        复用原任务：requalify 通过后 state_machine.transition(retry_candidate → creating)，
        继续 SPU/SKU/图 → 审核 → 上架/拒审流程；返回结构与 submit 相同。
        """
        task = self.repo.get_task(task_id)
        if task is None:
            return {
                "ok": False,
                "stage": "requalify",
                "error_code": "NO_MATCH",
                "evidence": {"task_id": task_id, "reason": "任务不存在"},
            }
        if task.status != "retry_candidate":
            return {
                "ok": False,
                "stage": "requalify",
                "error_code": "UNEXPECTED",
                "evidence": {
                    "task_id": task_id,
                    "status": task.status,
                    "reason": "仅 retry_candidate 任务可重提（P4 二次门禁）",
                },
            }

        # 0) REC-融合 P0-1：类目记忆预填（重提同样享受记忆预填，gate 前）
        candidate, prefill = self._prefill_from_category_memory(candidate)

        # P4 二次门禁：rejection.requalify 用 ListingGate 全量校验，passed 才放行
        if not self.rejection.requalify(task, candidate):
            return {
                "ok": False,
                "stage": "requalify",
                "gate_result": self.gate.evaluate(candidate).model_dump(),
                "category_memory": prefill,
            }

        task = self.state_machine.transition(
            task, "creating", evidence={"requalified": True}
        )
        if prefill:
            self.repo.append_op_log(
                task_id=task_id,
                api="category_memory_prefill",
                direction="prefill",
                payload_digest="",
                evidence_json=json.dumps(prefill, ensure_ascii=False),
            )
        return self._upload_and_audit(task, candidate, prefill)

    # ------------------------------------------------------------ 上传+审核（4~7 步共用）

    def _upload_and_audit(
        self,
        task: ListingTask,
        candidate: ListingCandidate,
        prefill: Optional[dict[str, Any]] = None,
    ) -> dict:
        """SPU/SKU/图片上传 → draft → 提交审核 → 查审 → 上架/拒审分流（断点续跑）。

        任何异常 → 结构化失败，任务状态留在最近合法状态（不伪造状态）。
        """
        task_id = task.task_id
        stage = "creating"
        try:
            # 4) create_spu → create_skus → upload_image（主图×N + 详情图）
            freight = (
                candidate.purchase_settings.freight_template_id
                if candidate.purchase_settings
                else None
            )
            pl = (
                candidate.purchase_settings.purchase_limit
                if candidate.purchase_settings
                else None
            )
            create_spu_payload = {
                "title": candidate.title,
                "category_id": candidate.category_id,
                "freight_template_id": self._to_int(freight),
                "purchase_limit": self._to_int((pl or {}).get("per_user")),
            }
            create_spu_result = self.adapter.create_spu(
                title=candidate.title,
                category_id=candidate.category_id,
                qualification=candidate.qualification,
                freight_template_id=create_spu_payload["freight_template_id"],
                purchase_limit=create_spu_payload["purchase_limit"],
                task_id=task_id,
            )
            self._log_api(task_id, "create_spu", "request", payload=create_spu_payload)
            self._log_api(task_id, "create_spu", "response", result=create_spu_result)
            spu_id = create_spu_result["spu_id"]
            task = self.repo.update_status(task_id, "creating", platform_spu_id=spu_id)

            # DA-009 集成修复：SPU 落库（listing_spus，幂等 upsert）——M5 候选池依赖
            self.repo.upsert_spu(
                spu_id=spu_id,
                task_id=task_id,
                title=candidate.title,
                category_id=candidate.category_id,
                qualification=candidate.qualification,
                freight_template_id=create_spu_payload["freight_template_id"],
                purchase_limit=pl,
                status="draft",
            )

            skus_payload = [
                {
                    "code": s.code,
                    "price_cents": s.price_cents,
                    "cost_cents": s.cost_cents,
                }
                for s in candidate.skus
            ]
            create_skus_result = self.adapter.create_skus(spu_id, skus_payload, task_id=task_id)
            self._log_api(task_id, "create_skus", "request", payload={"spu_id": spu_id, "skus": skus_payload})
            self._log_api(task_id, "create_skus", "response", result=create_skus_result)

            # DA-009 集成修复：SKU 落库（listing_skus，批量幂等 upsert）——M5 候选池价格依赖
            platform_sku_ids = create_skus_result.get("sku_ids") or []
            self.repo.upsert_skus(
                spu_id,
                [
                    {
                        "sku_id": platform_sku_ids[i] if i < len(platform_sku_ids) else f"mock_sku_{i}",
                        "product_sku_code": s.code,
                        "price_cents": s.price_cents,
                        "cost_cents": s.cost_cents,
                        "stock": 10000,
                    }
                    for i, s in enumerate(candidate.skus)
                ],
            )

            media_ids: list[str] = []
            for path in candidate.main_images:
                media_ids.append(
                    self.adapter.upload_image(path, "main_image", task_id=task_id)["media_id"]
                )
            for path in candidate.detail_images:
                media_ids.append(
                    self.adapter.upload_image(path, "detail_image", task_id=task_id)["media_id"]
                )
            self._log_api(
                task_id,
                "upload_image",
                "response",
                result={"media_ids": media_ids, "count": len(media_ids)},
            )

            task = self.state_machine.transition(task, "draft")
            stage = "draft"

            # 5) submit_audit → platform_auditing
            submit_result = self.adapter.submit_audit(spu_id, media_ids, task_id=task_id)
            self._log_api(
                task_id,
                "submit_audit",
                "request",
                payload={"spu_id": spu_id, "media_id_count": len(media_ids)},
            )
            self._log_api(task_id, "submit_audit", "response", result=submit_result)
            audit_id = submit_result["audit_id"]
            # DA-009：提交审核后回填 SPU audit_id/status（listing_spus 幂等更新）
            self.repo.upsert_spu(
                spu_id=spu_id,
                task_id=task_id,
                title=candidate.title,
                category_id=candidate.category_id,
                qualification=candidate.qualification,
                freight_template_id=create_spu_payload["freight_template_id"],
                purchase_limit=pl,
                status="platform_auditing",
                audit_id=audit_id,
            )
            task = self.state_machine.transition(
                task, "platform_auditing", evidence={"audit_id": audit_id}
            )
            stage = "platform_auditing"

            # 6) 查审分流
            audit_result = self.adapter.query_audit_status(audit_id, task_id=task_id)
            self._log_api(task_id, "query_audit_status", "response", result=audit_result)
            audit_status = audit_result.get("audit_status")

            if audit_status == "pass":
                link_result = self.adapter.get_product_link(spu_id, task_id=task_id)
                self._log_api(task_id, "get_product_link", "response", result=link_result)
                url = str(link_result.get("product_link") or "")
                # R22：链接验证通过才可迁移 listed（link_url 非空 + verified=True）
                if url and self.link_verifier(url):
                    task = self.state_machine.transition(
                        task, "listed", evidence={"link_url": url, "verified": True}
                    )
                    # REC-融合 P0-1：上架成功 → 类目提交计数（通过，streak+1），
                    # 供拒审率/连续拒审阈值判定（拒审转人工）
                    category = (candidate.category_name or "").strip()
                    if category:
                        self.repo.record_category_submission(category, rejected=False)
                    return {
                        "ok": True,
                        "stage": "listed",
                        "task_id": task_id,
                        "product_link": url,
                        "evidence": {
                            "link_url": url,
                            "verified": True,
                            "link_verified_at": task.link_verified_at,
                            "category_memory": prefill or {},
                        },
                    }
                # R22 负面：链接验证失败 → 不迁移 listed，状态停留 platform_auditing
                return {
                    "ok": False,
                    "stage": "link_verify",
                    "error_code": "UNEXPECTED",
                    "task_id": task_id,
                    "evidence": {
                        "task_id": task_id,
                        "link_url": url,
                        "verified": False,
                        "reason": "链接验证失败，R22 铁律拒绝标记 listed",
                        "category_memory": prefill or {},
                    },
                }

            # 驳回路径：rejected → rejection.handle → retry_candidate | manual
            reject_reason = str(audit_result.get("reject_reason") or "")
            analysis = self.rejection.analyze(reject_reason)
            # REC-融合 P0-1：类目拒审率 ≥50% 或连续图片拒审 ≥3 → 强制转人工复核
            # （即使有自动修复候选也不自动重提，防拒审风暴，decisions D14）
            category = (candidate.category_name or "").strip()
            manual_review = bool(category) and self.repo.should_manual_review_category(
                category
            )
            task = self.state_machine.transition(
                task, "rejected", evidence={"reject_reason_code": analysis.category}
            )
            rejection_result = self.rejection.handle(
                task, reject_reason, force_manual=manual_review
            )
            if category:
                self.repo.record_category_submission(category, rejected=True)
            return {
                "ok": True,
                "stage": rejection_result.action,
                "task_id": task_id,
                "evidence": {
                    "rejected": True,
                    "category": rejection_result.category,
                    "action": rejection_result.action,
                    "category_manual_review": manual_review,
                    "reject_reason": reject_reason,
                    "fix_candidates": [
                        c.model_dump() for c in rejection_result.analysis.fix_candidates
                    ],
                    "category_memory": prefill or {},
                },
            }
        except WechatApiError as exc:
            return self._fail(task_id, stage, exc.error_code, exc.evidence)
        except (IllegalTransitionError, ListedLinkVerificationError) as exc:
            return self._fail(task_id, stage, "UNEXPECTED", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001 兜底：结构化失败，不伪造状态
            return self._fail(task_id, stage, "UNEXPECTED", {"message": str(exc)})

    # ------------------------------------------------------------ 工具

    def _prefill_from_category_memory(
        self, candidate: ListingCandidate
    ) -> tuple[ListingCandidate, dict[str, Any]]:
        """REC-融合 P0-1：上架类目记忆预填（旧系统 category_listing_memory 迁移）。

        读取 listing_category_memory（键=candidate.category_name）：
        - logistics_template → 预填 purchase_settings.freight_template_id（仅当
          调用方显式未提供；预填发生在 gate 之前，预填字段参与门禁——缺运费模板
          的单不再因无记忆字段被拦）；
        - required_fields → 仅记入 evidence（C2 attrs_complete 门禁由迁移子代理
          落地，本处只读取标记，不重复实现，避免与在途迁移冲突）；
        - return_address_rule → 记入 evidence 供人工确认环节参照。
        不覆盖显式值；无记忆/类目为空 → 原样返回。
        返回 (候选, 预填证据 dict)。
        """
        category = (candidate.category_name or "").strip()
        if not category:
            return candidate, {}
        memory = self.repo.get_category_memory(category)
        if memory is None:
            return candidate, {}

        prefill: dict[str, Any] = {
            "category": category,
            "applied": False,
        }
        purchase = candidate.purchase_settings
        logistics = memory.get("logistics_template")
        if logistics and (
            purchase is None or not (purchase.freight_template_id or "").strip()
        ):
            if purchase is None:
                purchase = PurchaseSettings()
            purchase.freight_template_id = logistics
            prefill["applied"] = True
            prefill["freight_template_id"] = logistics
        if memory.get("required_fields"):
            prefill["required_fields"] = memory["required_fields"]
        if memory.get("return_address_rule"):
            prefill["return_address_rule"] = memory["return_address_rule"]
        if purchase is not candidate.purchase_settings:
            candidate = candidate.model_copy(update={"purchase_settings": purchase})
        return candidate, prefill

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    def _log_api(
        self,
        task_id: str,
        api: str,
        direction: str,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """证据留痕：payload_digest 为脱敏摘要（绝不落敏感值）；result 证据 JSON。"""
        payload_digest = None
        if payload is not None:
            payload_digest = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:16]
        evidence_json = None
        if result is not None:
            evidence_json = json.dumps({"result": result}, ensure_ascii=False, default=str)
        self.repo.append_op_log(
            task_id=task_id,
            api=api,
            direction=direction,
            payload_digest=payload_digest,
            evidence_json=evidence_json,
        )

    @staticmethod
    def _fail(
        task_id: str,
        stage: str,
        error_code: str,
        evidence: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "ok": False,
            "stage": stage,
            "error_code": error_code,
            "task_id": task_id,
            "evidence": evidence or {},
        }
