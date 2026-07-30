"""Citation curation and public evidence policy for clause-grounded answers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

WEAK_META_MARKERS = (
    "文档名称：",
    "产品名称：",
    "文档类型：",
    "生效日期：",
    "状态：演示样本",
    "状态：演示",
)

CLAUSE_MARKERS = (
    "等待期",
    "犹豫期",
    "责任免除",
    "免赔",
    "保险责任",
    "保险金",
    "本合同",
    "投保人",
    "被保险人",
    "理赔",
    "除外",
    "第",
    "条",
)


def chunk_text(chunk: Dict[str, Any]) -> str:
    content = chunk.get("content")
    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


def is_weak_citation_chunk(chunk: Dict[str, Any]) -> bool:
    """Return True for cover/metadata-only snippets that should not lead citations."""
    text = chunk_text(chunk).strip()
    if not text:
        return True
    if len(text) < 40 and not any(marker in text for marker in CLAUSE_MARKERS):
        return True
    meta_hits = sum(1 for marker in WEAK_META_MARKERS if marker in text)
    clause_hits = sum(1 for marker in CLAUSE_MARKERS if marker in text)
    if meta_hits >= 2 and clause_hits <= 1 and len(text) < 280:
        return True
    if meta_hits >= 3 and clause_hits == 0:
        return True
    return False


def doc_page_key(chunk: Dict[str, Any]) -> str:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    name = (
        chunk.get("document_name")
        or metadata.get("document_title")
        or metadata.get("filename")
        or metadata.get("source")
        or "unknown"
    )
    page = chunk.get("page_number")
    if page is None:
        page = metadata.get("page_number")
    return f"{str(name).strip().lower()}|{page}"


def relevance_bonus(question: str, chunk: Dict[str, Any]) -> float:
    question_text = question or ""
    text = chunk_text(chunk)
    bonus = 0.0
    for keyword in (
        "等待期",
        "犹豫期",
        "责任免除",
        "免赔额",
        "免赔",
        "酒驾",
        "自杀",
        "重大疾病",
        "身故",
        "理赔",
    ):
        if keyword in question_text and keyword in text:
            bonus += 0.15
    if any(marker in text for marker in CLAUSE_MARKERS):
        bonus += 0.05
    if is_weak_citation_chunk(chunk):
        bonus -= 0.5
    return bonus


def normalize_sim(score: Any) -> float:
    try:
        value = float(score)
    except Exception:
        return 0.0
    if 0.0 <= value <= 1.0:
        return value
    if value > 1.0:
        if value <= 2.0:
            return max(0.0, min(1.0, 1.0 - value))
        return max(0.0, min(1.0, 1.0 / (1.0 + value)))
    return 0.0


def chunk_gate_score(chunk: Dict[str, Any]) -> float:
    """Score used by refusal gate: prefer cosine vector_score over RRF (~0.03)."""
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    ranking_details = (
        metadata.get("ranking_details")
        if isinstance(metadata.get("ranking_details"), dict)
        else {}
    )
    preferred = [
        ranking_details.get("original_similarity"),
        metadata.get("vector_score"),
        chunk.get("vector_score"),
    ]
    best = 0.0
    for score in preferred:
        if score is not None:
            best = max(best, normalize_sim(score))
    if best > 0:
        return best

    fallback = [
        chunk.get("similarity_score"),
        metadata.get("bm25_score"),
        ranking_details.get("final_score"),
        metadata.get("rrf_score"),
    ]
    for score in fallback:
        if score is not None:
            best = max(best, normalize_sim(score))
    return best


def best_similarity(chunks: List[Dict[str, Any]]) -> float:
    best = 0.0
    for chunk in chunks or []:
        try:
            best = max(best, chunk_gate_score(chunk))
        except Exception:
            continue
    return best


def curate_citations(
    chunks: List[Dict[str, Any]],
    question: str = "",
    *,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    """Dedupe + drop weak cover chunks + keep top-N for answer [1]..[N]."""
    if not chunks:
        return []
    limit = max(1, min(int(limit or 4), 8))
    scored: List[tuple[float, int, Dict[str, Any]]] = []
    for idx, raw in enumerate(chunks):
        if not isinstance(raw, dict):
            continue
        chunk = dict(raw)
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        if not chunk.get("document_name"):
            chunk["document_name"] = (
                metadata.get("document_title")
                or metadata.get("filename")
                or metadata.get("display_name")
                or "未知文档"
            )
        if chunk.get("page_number") is None and metadata.get("page_number") is not None:
            chunk["page_number"] = metadata.get("page_number")
        if not chunk.get("content"):
            chunk["content"] = chunk_text(chunk)

        try:
            base = float(chunk.get("similarity_score") or 0.0)
        except Exception:
            base = 0.0
        try:
            for key in ("rrf_score", "final_score", "bm25_score", "vector_score"):
                if metadata.get(key) is not None:
                    base = max(base, float(metadata.get(key)))
        except Exception:
            pass

        score = base + relevance_bonus(question, chunk)
        if is_weak_citation_chunk(chunk):
            score -= 1.0
        scored.append((score, idx, chunk))

    scored.sort(key=lambda item: (-item[0], item[1]))
    strong = [item for item in scored if not is_weak_citation_chunk(item[2])]
    pool = strong if strong else scored
    selected: List[Dict[str, Any]] = []
    seen_pages: set[str] = set()
    seen_prefix: set[str] = set()
    for _score, _idx, chunk in pool:
        key = doc_page_key(chunk)
        text = chunk_text(chunk).strip()
        prefix = text[:48]
        if key in seen_pages:
            continue
        if prefix and prefix in seen_prefix:
            continue
        seen_pages.add(key)
        if prefix:
            seen_prefix.add(prefix)
        selected.append(chunk)
        if len(selected) >= limit:
            break
    if not selected:
        selected = [item[2] for item in scored[:limit]]
    return selected


def public_citations(
    chunks: List[Dict[str, Any]],
    *,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """Keep only chunks with a real similarity for UI/API honesty."""
    public: List[Dict[str, Any]] = []
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        try:
            score = float(chunk_gate_score(chunk))
        except Exception:
            try:
                score = float(chunk.get("similarity_score") or 0.0)
            except Exception:
                score = 0.0
        if score <= float(min_score or 0.0):
            continue
        if is_weak_citation_chunk(chunk):
            continue
        item = dict(chunk)
        item["similarity_score"] = round(max(0.0, min(1.0, score)), 4)
        public.append(item)
    return public


def citations_for_kind(
    kind: str,
    chunks: List[Dict[str, Any]],
    *,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Policy: refusal/advice/degraded -> no public sources; answer keeps scored ones."""
    normalized_kind = (kind or "answer").lower()
    if normalized_kind in ("refusal", "advice", "degraded", "insufficient_evidence"):
        return []
    threshold = min_score
    if threshold is None or float(threshold) <= 0.0:
        threshold = 0.05
    return public_citations(chunks, min_score=float(threshold))
