"""M5 自动小店投放（商品托管）· 监控回读（v0.4 监控层第一部分）。

定时回读投放管理列表（商品曝光数/花费/成交金额/平台补贴/智能诊断/状态），解析为
结构化快照入库 ad_report_snapshots（(campaign_id, recorded_at) 唯一约束幂等，
D-M5-06：同周期仅保留最新快照），支持断点补快照（collect_missing：已存在跳过、
since 过滤、缺失补齐）。

本文件为纯数据驱动（fixtures/mock），不依赖真实浏览器/登录态：输入为一行原始
投放列表 dict（fixtures 模拟后台表格行），输出为规范化快照行 + repo.upsert_snapshot
幂等入库。真实页面读取（Playwright 适配器）后续接入，本层接口不变——真实适配器
把页面行转成相同 dict 结构交给 run_once/collect_missing 即可。

口径（data-audit DA-001）：
- 金额一律「分」（int）：后台展示为元，字符串输入按 元→分（×100 四舍五入）；
  数值（int/float）输入按「分」直接取整（不乘 100）。
- 时间一律 UTC 带时区（recorded_at 缺省用当前 UTC；带偏移字符串转 UTC）。
- 枚举英文（中文仅注释/展示映射）：
  诊断  excellent / good / optimize_1 / optimize_n / unknown；
  状态  active / paused / not_eligible / pending / ended / unknown。

本文件不新增表（只使用既有 ad_report_snapshots）、不改动既有文件；
不做真实定时器（调度归后续集成/总控），仅提供 run_once/collect_missing 幂等入口
+ next_run_hint 建议时间（config.report_interval_s 只读作默认间隔）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import repo
from .models import ensure_aware, utcnow

# ---------------------------------------------------------------- 常量

# 诊断归一化：精确中文 → 英文枚举（08 文档：后台智能诊断展示 优秀/良好/1项待优化/N项待优化）
_DIAGNOSIS_EXACT: dict[str, str] = {
    "优秀": "excellent",
    "良好": "good",
}
# N项待优化（N≥1）：正则命中后按 N==1 → optimize_1，N≥2 → optimize_n
_DIAGNOSIS_OPTIMIZE_RE = re.compile(r"(\d+)\s*项待优化")

# 状态归一化：精确中文 → 英文枚举（对齐后台投放管理列表筛选：全部/投放中/暂停投放/不可投放）
_STATUS_EXACT: dict[str, str] = {
    "投放中": "active",
    "已暂停": "paused",
    "暂停投放": "paused",
    "不可投放": "not_eligible",
    "待托管": "pending",
    "已结束": "ended",
}

# 金额字段（元→分解析走 parse_amount_fen）
_AMOUNT_FIELDS: tuple[str, ...] = ("spend", "gmv", "platform_subsidy")


# ---------------------------------------------------------------- 归一化纯函数
def normalize_diagnosis(raw: str | None) -> str:
    """中文诊断 → 英文枚举（大小写/空白容忍：strip 后匹配）。

    优秀→excellent；良好→good；`(\d+)项待优化`：N==1→optimize_1、N≥2→optimize_n；
    空/未知（含英文输入、0项待优化）→unknown。
    """
    if raw is None:
        return "unknown"
    text = raw.strip()
    if not text:
        return "unknown"
    exact = _DIAGNOSIS_EXACT.get(text)
    if exact is not None:
        return exact
    m = _DIAGNOSIS_OPTIMIZE_RE.search(text)
    if m is not None:
        n = int(m.group(1))
        if n == 1:
            return "optimize_1"
        if n >= 2:
            return "optimize_n"
    return "unknown"


def normalize_status(raw: str | None) -> str:
    """投放列表状态 → 英文枚举（strip 后匹配）。

    投放中→active；暂停（投放）/已暂停/暂停→paused（凡以「暂停」开头均按 paused）；
    不可投放→not_eligible；待托管→pending；已结束→ended；空/未知→unknown。
    """
    if raw is None:
        return "unknown"
    text = raw.strip()
    if not text:
        return "unknown"
    exact = _STATUS_EXACT.get(text)
    if exact is not None:
        return exact
    if text.startswith("暂停"):
        return "paused"
    return "unknown"


def parse_amount_fen(raw: str | float | int | None, default: int = 0) -> int:
    """金额解析（口径 DA-001，单位：分）。

    - str：后台展示为元 → 按元解析（去千分位逗号 → float → ×100 四舍五入），
      如 "12.34"→1234、"1,234.56"→123456、"1234"→123400（字符串一律按元！）；
    - int/float：输入即「分」，直接取整（截断），如 1234→1234、12.9→12；
    - None/非法（空串/非数字/含多余小数点）→ default（默认 0）。
    """
    if raw is None or isinstance(raw, bool):  # bool 是 int 子类，按非法处理
        return default
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if not text:
            return default
        try:
            yuan = float(text)
        except ValueError:
            return default
        # 元→分：×100 四舍五入（金额非负，round 半进半舍偏差可忽略，注释口径：四舍五入）
        return int(round(yuan * 100))
    return default


# ---------------------------------------------------------------- 快照行解析
def _as_utc(dt: datetime) -> datetime:
    """统一为 UTC 带时区：naive 视为 UTC 补时区；带偏移转 UTC（DA-001）。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_recorded_at(value: Any) -> datetime:
    """recorded_at 解析：None→当前 UTC；str→ISO8601（含 Z/偏移）；datetime→转 UTC。非法抛 ValueError。"""
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("recorded_at 为空字符串")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"recorded_at 格式非法: {value!r}") from exc
        return _as_utc(dt)
    raise ValueError(f"recorded_at 类型非法: {type(value).__name__}")


def _to_int(value: Any, default: int = 0) -> int:
    """整型字段（impressions）解析：缺失/非法 → default；字符串容忍千分位逗号。"""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    return default


def parse_snapshot_row(raw: dict) -> dict:
    """一行原始投放列表 dict → 规范化快照 dict（字段超集，含 raw_json 副本）。

    输入（fixtures 模拟投放管理列表行）：
        {campaign_id, impressions, spend, gmv, platform_subsidy,
         diagnosis, status, recorded_at?}
    输出：
        {campaign_id:int, recorded_at:datetime(UTC aware),
         impressions:int, spend/gmv/platform_subsidy:int(分),
         diagnosis/status:str(英文枚举), raw_json:dict(原始行副本)}

    - campaign_id 缺失/非法 → 抛 ValueError（上层收集器记 errors 失败隔离）；
    - recorded_at 缺失 → 当前 UTC；字符串非法 → 抛 ValueError；
    - 其余字段缺失/非法 → 默认值（impressions=0、金额=0、诊断/状态=unknown）。
    """
    if not isinstance(raw, dict):
        raise ValueError(f"原始行必须为 dict，收到 {type(raw).__name__}")

    cid_raw = raw.get("campaign_id")
    if cid_raw is None:
        raise ValueError("campaign_id 缺失")
    try:
        campaign_id = int(cid_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"campaign_id 非法: {cid_raw!r}") from exc

    parsed: dict[str, Any] = {
        "campaign_id": campaign_id,
        "recorded_at": _parse_recorded_at(raw.get("recorded_at")),
        "impressions": _to_int(raw.get("impressions")),
        "spend": parse_amount_fen(raw.get("spend")),
        "gmv": parse_amount_fen(raw.get("gmv")),
        "platform_subsidy": parse_amount_fen(raw.get("platform_subsidy")),
        "diagnosis": normalize_diagnosis(raw.get("diagnosis")),
        "status": normalize_status(raw.get("status")),
        "raw_json": dict(raw),  # 原始行副本（保留字段超集，供审计/断点重放）
    }
    return parsed


# ---------------------------------------------------------------- 收集结果
@dataclass
class CollectResult:
    """一次收集/补快照的结果统计。

    collected：解析成功并进入入库流程的行数（= upserted + skipped）；
    upserted ：实际执行 upsert_snapshot 的行数（幂等：存在则更新、不存在则新增）；
    skipped  ：跳过行数（collect_missing 中 (campaign_id, recorded_at) 已存在 / 无数据源）；
    errors   ：失败行 [{row: 行号(1 起), reason: 原因, raw: 脱敏后的原始行}]。
    """

    collected: int = 0
    upserted: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)


def _redact_raw(raw: Any) -> Any:
    """错误记录用轻量脱敏：字符串截断至 120 字符；无空白长串（类 Token）整体掩码。

    本层按宪法不涉及凭证字段，脱敏为防御性实现（防意外串入 Cookie/签名类文本）。
    """
    if not isinstance(raw, dict):
        return {"value": str(raw)[:120]}

    def _is_token(s: str) -> bool:
        return len(s) > 24 and not any(ch.isspace() for ch in s)

    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, str):
            s = v.strip()
            out[str(k)] = f"<redacted:len={len(s)}>" if _is_token(s) else s[:120]
        else:
            out[str(k)] = v
    return out


# ---------------------------------------------------------------- 快照收集器
class SnapshotCollector:
    """投放报表快照收集器（数据驱动/Mock，无真实浏览器）。

    session 用于 repo 调用（repo 层函数式风格，提交由调用方负责：如
    `with db.session() as s: SnapshotCollector(s).run_once(rows)`）；
    db 可选，供调度器集成时自管会话（db.new_session() 构造 + commit()）。
    """

    def __init__(self, session, db: Any = None):
        self.session = session
        self.db = db

    # ------------------------------------------------------------ 工具
    def commit(self) -> None:
        """显式提交当前会话（调度器集成时使用；fixtures 阶段通常由调用方提交）。"""
        self.session.commit()

    @staticmethod
    def _error_entry(idx: int, exc: Exception, raw: Any) -> dict:
        return {"row": idx, "reason": str(exc), "raw": _redact_raw(raw)}

    # ------------------------------------------------------------ 入口
    def run_once(self, rows: list[dict]) -> CollectResult:
        """全量回读一轮：逐行 parse_snapshot_row → repo.upsert_snapshot（幂等）。

        单行解析/入库失败 → 记 errors（含行号+原因+脱敏 raw）继续下一行（失败隔离，
        不整批崩）；同 (campaign_id, recorded_at) 重复 upsert 只更新不新增。
        """
        result = CollectResult()
        for idx, row in enumerate(rows, start=1):
            try:
                parsed = parse_snapshot_row(row)
            except Exception as exc:  # noqa: BLE001 —— 失败隔离：单行解析失败不影响整批
                result.errors.append(self._error_entry(idx, exc, row))
                continue
            try:
                with self.session.begin_nested():  # 每行独立 savepoint：入库失败仅回滚本行
                    repo.upsert_snapshot(
                        self.session,
                        campaign_id=parsed["campaign_id"],
                        recorded_at=parsed["recorded_at"],
                        impressions=parsed["impressions"],
                        spend=parsed["spend"],
                        gmv=parsed["gmv"],
                        platform_subsidy=parsed["platform_subsidy"],
                        diagnosis=parsed["diagnosis"],
                        status=parsed["status"],
                    )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(self._error_entry(idx, exc, row))
                continue
            result.collected += 1
            result.upserted += 1
        return result

    def collect_missing(
        self,
        campaign_ids: list[int],
        since: Optional[datetime] = None,
        rows: Optional[list[dict]] = None,
    ) -> CollectResult:
        """断点补快照：对指定 campaign 重跑（幂等由 (campaign_id, recorded_at) 唯一约束保证）。

        - rows：原始投放列表行（fixtures/真实读取适配器提供）。本层纯数据驱动，无数据源
          （rows=None）时无事可做，返回空结果；调度器集成时由真实读取适配器传入；
        - 只处理 campaign_id ∈ campaign_ids 且 recorded_at >= since（since 传入时）的行，
          since 之前的行整体排除（不计入 collected/skipped）；
        - 已存在 (campaign_id, recorded_at) 快照 → skipped；缺失 → upsert 补齐。
        """
        result = CollectResult()
        if rows is None:
            return result
        since = ensure_aware(since) if since is not None else None
        wanted = set(campaign_ids)
        # 预取各 campaign 已存在快照时间集（避免逐行查库；SQLite 读回 naive，补 UTC 统一比较）
        existing: dict[int, set[datetime]] = {
            cid: {ensure_aware(r.recorded_at) for r in repo.list_snapshots(self.session, campaign_id=cid)}
            for cid in wanted
        }
        for idx, row in enumerate(rows, start=1):
            try:
                parsed = parse_snapshot_row(row)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(self._error_entry(idx, exc, row))
                continue
            cid = parsed["campaign_id"]
            if cid not in wanted:
                continue  # 非目标 campaign：整体排除
            recorded_at = parsed["recorded_at"]
            if since is not None and recorded_at < since:
                continue  # since 之前的缺失周期不处理
            result.collected += 1
            if recorded_at in existing.get(cid, set()):
                result.skipped += 1
                continue
            try:
                with self.session.begin_nested():
                    repo.upsert_snapshot(
                        self.session,
                        campaign_id=cid,
                        recorded_at=recorded_at,
                        impressions=parsed["impressions"],
                        spend=parsed["spend"],
                        gmv=parsed["gmv"],
                        platform_subsidy=parsed["platform_subsidy"],
                        diagnosis=parsed["diagnosis"],
                        status=parsed["status"],
                    )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(self._error_entry(idx, exc, row))
                continue
            result.upserted += 1
            existing.setdefault(cid, set()).add(recorded_at)  # 批内去重：后续同周期行跳过
        return result

    @staticmethod
    def next_run_hint(
        interval_s: Optional[int] = None, last_run_at: Optional[datetime] = None
    ) -> datetime:
        """下次回读建议时间（UTC 带时区，供调度器使用）。

        interval_s 缺省时读 config.report_interval_s（只读默认值，不修改配置）；
        last_run_at 缺省以当前 UTC 为基准。本层不做真实定时器（调度归后续集成）。
        """
        return next_run_hint(interval_s, last_run_at)


def next_run_hint(
    interval_s: Optional[int] = None, last_run_at: Optional[datetime] = None
) -> datetime:
    """下次回读建议时间（UTC 带时区）。interval_s 缺省 → config.report_interval_s 只读默认。"""
    if interval_s is None:
        from .config import load_config  # 惰性导入：仅缺省时需要

        interval_s = load_config().report_interval_s
    base = ensure_aware(last_run_at) if last_run_at is not None else utcnow()
    return base + timedelta(seconds=int(interval_s))


__all__ = [
    "CollectResult",
    "SnapshotCollector",
    "next_run_hint",
    "normalize_diagnosis",
    "normalize_status",
    "parse_amount_fen",
    "parse_snapshot_row",
]
