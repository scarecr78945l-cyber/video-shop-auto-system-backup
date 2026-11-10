"""T2: 60 enum migration (generated from enum-registry.yaml, round-51)

Revision ID: 60enum000000
Revises: 32f34131a28a
Create Date: 2026-09-03T12:00:00+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


revision: str = '60enum000000'
down_revision: Union[str, Sequence[str], None] = '32f34131a28a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENUMS = [
    ('enum_entity_status', ['active', 'suspended', 'archived']),
    ('enum_product_status', ['draft', 'active', 'archived']),
    ('enum_asset_status', ['active', 'archived', 'rejected']),
    ('enum_health_state', ['healthy', 'degraded', 'cooldown', 'manual_required']),
    ('enum_platform', ['wechat_channels', 'douyin', 'youmi', 'luopan', 'taobao', 'alibaba']),
    ('enum_login_state', ['unknown', 'logged_in', 'expired', 'auth_required']),
    ('enum_account_status', ['draft', 'auth_pending', 'read_verified', 'config_verified', 'write_pending', 'write_verified', 'ready', 'suspended']),
    ('enum_profile_purpose', ['default', 'browser_automation', 'openapi']),
    ('enum_profile_status', ['active', 'broken', 'recalibrating']),
    ('enum_credential_purpose', ['cookie', 'token', 'openapi_secret', 'proxy_credential']),
    ('enum_credential_status', ['valid', 'expired', 'rotating', 'revoked']),
    ('enum_supplier_platform', ['1688', 'taobao', 'self', 'custom']),
    ('enum_fulfillment_mode', ['drop_ship', 'self_stock']),
    ('enum_common_source', ['manual', 'import', 'system']),
    ('enum_common_mode', ['real', 'mock', 'fixtures']),
    ('enum_asset_mode', ['real', 'mock', 'fixtures', 'pillow', 'ai_generated']),
    ('enum_offer_source', ['supplier_catalog', 'realtime_inquiry', 'manual']),
    ('enum_offer_preferred', ['none', 'current', 'superseded']),
    ('enum_sku_compliance', ['ok', 'hard_reject', 'manual_review']),
    ('enum_decision_compliance', ['hard_reject', 'candidate', 'manual_review']),
    ('enum_sku_salable', ['salable', 'closed', 'insufficient_data']),
    ('enum_listing_sku_status', ['listed', 'closed', 'rejected', 'insufficient_data']),
    ('enum_snapshot_objtype', ['product', 'sku', 'shop_listing', 'shop_listing_sku']),
    ('enum_decision_source', ['board_snapshot', 'page_signal', 'supplier', 'manual']),
    ('enum_quote_status', ['none', 'pending', 'valid', 'expired']),
    ('enum_material_status', ['unknown', 'has_path', 'material_gap']),
    ('enum_decision_state', ['discovered', 'scored', 'approved', 'material_ready', 'listing_ready']),
    ('enum_asset_source_type', ['supplier_authorized', 'self_created', 'purchased_license', 'web_collected']),
    ('enum_rights_status', ['owned', 'authorized', 'licensed', 'pending_review', 'unknown', 'rejected']),
    ('enum_media_purpose', ['main_image', 'detail_image', 'ad_video', 'ad_image']),
    ('enum_shopbind_auth', ['pending', 'authorized', 'revoked']),
    ('enum_shopbind_review', ['pending', 'approved', 'rejected']),
    ('enum_review_scope', ['asset', 'asset_product', 'asset_shop', 'listing', 'campaign']),
    ('enum_review_type', ['source', 'rights', 'quality', 'ai_content', 'first_use', 're_submit']),
    ('enum_review_decision', ['approved', 'rejected', 'needs_rework']),
    ('enum_listing_status', ['draft', 'gate_pending', 'listing', 'on_sale', 'rejected', 'archived']),
    ('enum_pricing_type', ['initial', 'adjustment', 'promotion']),
    ('enum_pricing_status', ['draft', 'pending_approval', 'approved', 'rejected', 'superseded', 'expired']),
    ('enum_listevent_type', ['created', 'gate_retry', 'auto_fixed', 'submitted', 'audit_pass', 'audit_reject', 'manual_confirm', 'on_sale', 'archived']),
    ('enum_campaign_status', ['draft', 'pending_confirm', 'running', 'paused', 'stopped', 'ended', 'manual_review']),
    ('enum_snapshot_granularity', ['campaign', 'shop_listing', 'shop_listing_sku', 'campaign_asset']),
    ('enum_snapshot_diag', ['excellent', 'good', 'optimize_1', 'optimize_n', 'unknown']),
    ('enum_snapshot_status', ['active', 'paused', 'not_eligible', 'pending', 'ended', 'unknown']),
    ('enum_feedback_type', ['product_score', 'category_score', 'material_score', 'sku_margin', 'shop_strategy']),
    ('enum_feedback_subject', ['product', 'category', 'material', 'shop', 'sku']),
    ('enum_run_type', ['listing_flow', 'material_flow', 'selection_flow', 'ads_flow', 'full_chain']),
    ('enum_run_status', ['running', 'waiting_manual', 'paused', 'done', 'failed', 'cancelled']),
    ('enum_step_status', ['pending', 'running', 'gate_retry', 'manual_review', 'done', 'failed']),
    ('enum_task_type', ['login_assist', 'gate_override', 'material_review', 'listing_confirm', 'ads_confirm', 'report_manual', 'page_calibration']),
    ('enum_task_status', ['pending', 'in_progress', 'approved', 'rejected', 'resolved']),
    ('enum_policy_type', ['cid_breakeven', 'pricing', 'compliance', 'whitelist', 'budget', 'stop_loss', 'rate_limit', 'gate']),
    ('enum_policy_scope', ['global', 'platform_default', 'category', 'shop', 'product']),
    ('enum_alert_severity', ['critical', 'high', 'medium', 'low']),
    ('enum_alert_category', ['funds', 'account', 'platform', 'task', 'infra', 'data_quality']),
    ('enum_alert_status', ['open', 'acknowledged', 'escalated', 'recovering', 'resolved']),
    ('enum_delivery_channel', ['dashboard', 'wecom', 'email', 'telegram']),
    ('enum_delivery_notif', ['open', 'escalation', 'recovery']),
    ('enum_delivery_status', ['pending', 'retrying', 'sent', 'delivered', 'failed', 'dropped']),
    ('enum_actor_kind', ['user', 'system', 'worker', 'service']),
    ('enum_actor_status', ['active', 'disabled']),
]


def upgrade() -> None:
    """按 registry 顺序创建 60 enum（app schema，search_path 已设）。"""
    for name, values in _ENUMS:
        labels = ', '.join(repr(v) for v in values)
        op.execute(f'CREATE TYPE {name} AS ENUM ({labels})')


def downgrade() -> None:
    """严格逆序删除 60 enum。"""
    for name, _ in reversed(_ENUMS):
        op.execute(f'DROP TYPE {name}')

