"""Question-boundary and refusal wording policy for insurance clause RAG."""

from __future__ import annotations

from typing import Any, Dict, List

INSURANCE_KEYWORDS = [
    "保险",
    "条款",
    "等待期",
    "免赔",
    "责任免除",
    "犹豫期",
    "理赔",
    "保额",
    "身故",
    "重疾",
    "投保",
    "保单",
    "除外",
    "酒驾",
    "自杀",
]

ADVICE_OR_GUARANTEE_MARKERS = [
    "一定能获赔",
    "保证获赔",
    "该不该买",
    "应不应该买",
    "推荐购买",
    "帮我配置",
    "今天买",
    "保证理赔",
]

CHITCHAT_OR_OFFTOPIC_MARKERS = ["天气", "北京", "上海", "你好", "讲个笑话", "股票", "足球"]


def refusal_answer(reason: str = "insufficient_evidence") -> str:
    if reason == "advice":
        return """【结论】
本系统不能给出是否购买保险、是否一定获赔的建议或承诺。

【条款依据】
演示语料仅用于说明犹豫期、等待期、责任免除等条款检索；真实核保与理赔取决于正式合同与事故事实。

【不确定/边界】
本系统不构成保险销售或理赔承诺。"""
    return """【结论】
未在已入库条款中找到充分依据，无法就该问题给出有引用支撑的结论。

【条款依据】
当前检索结果为空或相关度不足，请换用条款中的术语（如等待期、免赔额、责任免除）重试。

【不确定/边界】
本系统不构成保险销售或理赔承诺。"""


def is_advice_or_guarantee_question(question: str) -> bool:
    question_text = (question or "").strip()
    return any(marker in question_text for marker in ADVICE_OR_GUARANTEE_MARKERS)


def is_off_topic(question: str, chunks: List[Dict[str, Any]]) -> bool:
    """Heuristic off-topic gate for demo corpus (weather / chit-chat)."""
    question_text = (question or "").strip()
    if any(keyword in question_text for keyword in INSURANCE_KEYWORDS):
        return False
    if any(keyword in question_text for keyword in CHITCHAT_OR_OFFTOPIC_MARKERS):
        return True
    if not chunks:
        return True
    top_text = chunks[0].get("content") or ""
    overlap = sum(1 for keyword in INSURANCE_KEYWORDS if keyword in top_text and keyword in question_text)
    return overlap == 0 and len(question_text) < 40 and not any(
        char in question_text for char in "等待免赔责任犹豫理赔保"
    )
