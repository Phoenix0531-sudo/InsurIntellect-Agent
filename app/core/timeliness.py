"""
时效性规则引擎
依据《人身保险产品备案管理办法》《数据安全法》等制度文本的原则，
对寿险产品销售语料进行时效性评估与打分，用于排序抑制过期文档、提升新近与在有效期内的内容。

设计要点：
- 优先使用元数据中的日期：effective_date / expiry_date(valid_until) / last_updated_date / publish_date。
- 若存在有效期(expiry_date)且已过期：时效性分数为0。
- 若处于生效前(pre-effective)：分数按系数降低。
- 结合保单/产品备案(filing_date)进行对齐，早于备案版本的内容降权。
- 对弱信号日期来源（如文件时间戳、目录年份占位）施加置信度降权。
- 遵循数据安全法的保留期限思想：若最后日期距今超过保留阈值视为过期（默认540天）。

返回分值范围：0~100（可通过settings.TIMELINESS_WEIGHT进行整体权重缩放）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional

from app.core.config import settings


WEAK_SOURCES = {"file_timestamp", "dir_year_placeholder"}


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    text = str(s).strip()
    if not text or text == "未知":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _best_date(metadata: Dict[str, Any]) -> Optional[datetime]:
    """在有效、生效、更新、发布日期中选择一个最合理的参考日期。"""
    candidates = [
        metadata.get("effective_date"),
        metadata.get("last_updated_date"),
        metadata.get("publish_date"),
    ]
    best: Optional[datetime] = None
    for d in candidates:
        dt = _parse_date(d)
        if dt and (best is None or dt > best):
            best = dt
    return best


def is_expired_doc(metadata: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """过期判定：
    - 若存在expiry_date(valid_until)且已过期 -> True
    - 否则以最佳参考日期与保留阈值比较（TIMELINESS_RETENTION_DAYS）
    """
    now = now or datetime.now()
    expiry = _parse_date(metadata.get("expiry_date") or metadata.get("valid_until"))
    if expiry and now > expiry:
        return True
    best = _best_date(metadata)
    if best is None:
        # 没有日期信息，视为不可信且过期（抑制）
        return True
    return (now - best).days >= settings.TIMELINESS_RETENTION_DAYS


def compute_timeliness_score(metadata: Dict[str, Any], now: Optional[datetime] = None) -> float:
    """计算时效性分数，范围0~100。

    规则：
    - 过期 -> 0
    - 基于参考日期的线性衰减（上限TIMELINESS_DECAY_CAP_DAYS），最近加分
    - 生效前降权（TIMELINESS_PRE_EFFECTIVE_PENALTY_FACTOR）
    - 弱信号日期来源降权（TIMELINESS_WEAK_SOURCE_PENALTY_FACTOR）
    - 早于产品备案版本(filing_date)降权
    """
    now = now or datetime.now()

    # 过期直接返回0
    if is_expired_doc(metadata, now=now):
        return 0.0

    effective = _parse_date(metadata.get("effective_date"))
    last_ref = _best_date(metadata)
    base_date = effective or last_ref

    score = 0.0
    if base_date:
        days = max(0, (now - base_date).days)
        cap = max(1, settings.TIMELINESS_DECAY_CAP_DAYS)
        # 将剩余有效期映射到0~100分
        remaining = max(0, cap - days)
        score = (remaining / cap) * 100.0

        # 最近加分
        if days <= settings.TIMELINESS_RECENT_BONUS_DAYS:
            score += settings.TIMELINESS_RECENT_BONUS

    # 生效前降权
    if effective and now < effective:
        score *= settings.TIMELINESS_PRE_EFFECTIVE_PENALTY_FACTOR

    # 弱信号来源降权
    source = str(metadata.get("date_source", "")).strip()
    if source in WEAK_SOURCES:
        score *= settings.TIMELINESS_WEAK_SOURCE_PENALTY_FACTOR

    # 备案版本对齐：若内容日期早于备案版本日期，整体降权
    filing_dt = _parse_date(metadata.get("filing_date"))
    if filing_dt and base_date and base_date < filing_dt:
        score *= 0.8

    # 保证范围
    return float(max(0.0, min(score, 100.0)))


__all__ = [
    "compute_timeliness_score",
    "is_expired_doc",
]

