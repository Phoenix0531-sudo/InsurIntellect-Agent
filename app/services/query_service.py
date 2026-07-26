"""
查询服务
整合向量搜索和LLM生成,提供完整的问答功能
"""

from datetime import datetime
import asyncio
from typing import List, Dict, Any, Optional
import json
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.core.config import settings
from app.core.app_logging import get_logger
from app.models.database_models import QueryHistory, Document, DocumentChunk
from app.models.schemas import QueryRequest, QueryResponse, RetrievedChunk, QueryStatistics
from app.core.rag_workflow import get_agent
from app.core.database import db_manager
from app.services.llm_service import LLMService
from app.services.query_rewriter_service import QueryRewriterService
from app.services.query_router_service import QueryRouterService
from app.services.text_to_sql_service import TextToSQLService
from app.services.kg_service import KGService

logger = get_logger(__name__)


class QueryService:
    """查询服务"""
    
    def __init__(self):
        """初始化查询服务,使用InsurIntellectAgent RAG工作流"""
        # 延迟初始化agent,避免在服务启动时就创建
        self._agent = None

    @property
    def agent(self):
        """获取agent实例,使用延迟初始化"""
        if self._agent is None:
            logger.info("初始化agent实例...")
            try:
                self._agent = get_agent()
                logger.info(f"Agent实例初始化成功: {type(self._agent)}")
            except Exception as e:
                logger.error(f"Agent实例初始化失败: {e}", exc_info=True)
                raise
        return self._agent

    @property
    def embedding_service(self):
        """Expose agent embedding service for provider metadata on responses."""
        try:
            return getattr(self.agent, "embedding_service", None)
        except Exception:
            return None

    # Cover / metadata-only lines that are weak as citations.
    _WEAK_META_MARKERS = (
        "文档名称：",
        "产品名称：",
        "文档类型：",
        "生效日期：",
        "状态：演示样本",
        "状态：演示",
    )
    _CLAUSE_MARKERS = (
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

    def _chunk_text(self, c: Dict[str, Any]) -> str:
        content = c.get("content")
        if content is None:
            return ""
        return content if isinstance(content, str) else str(content)

    def _is_weak_citation_chunk(self, c: Dict[str, Any]) -> bool:
        """True for cover/metadata-only snippets that should not lead citations."""
        text = self._chunk_text(c).strip()
        if not text:
            return True
        if len(text) < 40 and not any(m in text for m in self._CLAUSE_MARKERS):
            return True
        meta_hits = sum(1 for m in self._WEAK_META_MARKERS if m in text)
        clause_hits = sum(1 for m in self._CLAUSE_MARKERS if m in text)
        if meta_hits >= 2 and clause_hits <= 1 and len(text) < 280:
            return True
        if meta_hits >= 3 and clause_hits == 0:
            return True
        return False

    def _doc_page_key(self, c: Dict[str, Any]) -> str:
        md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        name = (
            c.get("document_name")
            or md.get("document_title")
            or md.get("filename")
            or md.get("source")
            or "unknown"
        )
        page = c.get("page_number")
        if page is None:
            page = md.get("page_number")
        return f"{str(name).strip().lower()}|{page}"

    def _relevance_bonus(self, question: str, c: Dict[str, Any]) -> float:
        q = question or ""
        text = self._chunk_text(c)
        bonus = 0.0
        for kw in (
            "等待期", "犹豫期", "责任免除", "免赔额", "免赔",
            "酒驾", "自杀", "重大疾病", "身故", "理赔",
        ):
            if kw in q and kw in text:
                bonus += 0.15
        if any(m in text for m in self._CLAUSE_MARKERS):
            bonus += 0.05
        if self._is_weak_citation_chunk(c):
            bonus -= 0.5
        return bonus

    def curate_citations(
        self,
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
            c = dict(raw)
            md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
            if not c.get("document_name"):
                c["document_name"] = (
                    md.get("document_title")
                    or md.get("filename")
                    or md.get("display_name")
                    or "未知文档"
                )
            if c.get("page_number") is None and md.get("page_number") is not None:
                c["page_number"] = md.get("page_number")
            if not c.get("content"):
                c["content"] = self._chunk_text(c)
            try:
                base = float(c.get("similarity_score") or 0.0)
            except Exception:
                base = 0.0
            try:
                if isinstance(md, dict):
                    for k in ("rrf_score", "final_score", "bm25_score", "vector_score"):
                        if md.get(k) is not None:
                            base = max(base, float(md.get(k)))
            except Exception:
                pass
            score = base + self._relevance_bonus(question, c)
            if self._is_weak_citation_chunk(c):
                score -= 1.0
            scored.append((score, idx, c))
        scored.sort(key=lambda t: (-t[0], t[1]))
        strong = [t for t in scored if not self._is_weak_citation_chunk(t[2])]
        pool = strong if strong else scored
        selected: List[Dict[str, Any]] = []
        seen_pages: set = set()
        seen_prefix: set = set()
        for _score, _idx, c in pool:
            key = self._doc_page_key(c)
            text = self._chunk_text(c).strip()
            prefix = text[:48]
            if key in seen_pages:
                continue
            if prefix and prefix in seen_prefix:
                continue
            seen_pages.add(key)
            if prefix:
                seen_prefix.add(prefix)
            selected.append(c)
            if len(selected) >= limit:
                break
        if not selected:
            selected = [t[2] for t in scored[:limit]]
        return selected



    def public_citations(
        self,
        chunks: List[Dict[str, Any]],
        *,
        for_ui: bool = True,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Keep only chunks with a real similarity for UI/API honesty.

        Padding / zero-score fillers are dropped so refusal and weak hits
        do not look like fake evidence.
        """
        out: List[Dict[str, Any]] = []
        for c in chunks or []:
            if not isinstance(c, dict):
                continue
            try:
                score = float(self._chunk_gate_score(c))
            except Exception:
                try:
                    score = float(c.get("similarity_score") or 0.0)
                except Exception:
                    score = 0.0
            if score <= float(min_score or 0.0):
                continue
            if self._is_weak_citation_chunk(c):
                continue
            cc = dict(c)
            # store normalized score for display honesty
            cc["similarity_score"] = round(max(0.0, min(1.0, score)), 4)
            out.append(cc)
        return out

    def citations_for_kind(
        self,
        kind: str,
        chunks: List[Dict[str, Any]],
        *,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Policy: refusal/advice/degraded -> no public sources; answer keeps scored ones."""
        k = (kind or "answer").lower()
        if k in ("refusal", "advice", "degraded", "insufficient_evidence"):
            return []
        thr = min_score
        # for answer / llm_unavailable keep real cosine-like scores;
        # drop pure RRF filler ranks (~0.03) that look like fake evidence.
        if thr is None or float(thr) <= 0.0:
            thr = 0.05
        return self.public_citations(chunks, min_score=float(thr))

    def _to_retrieved_chunks(self, chunks: List[Dict[str, Any]]) -> List[RetrievedChunk]:
        """Normalize raw retrieval dicts into RetrievedChunk models."""
        normalized: List[RetrievedChunk] = []
        for c in chunks or []:
            md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}

            chunk_id_raw = c.get("chunk_id") if c.get("chunk_id") is not None else md.get("chunk_id")
            chunk_id_val: Any = -1
            if isinstance(chunk_id_raw, int):
                chunk_id_val = chunk_id_raw
            elif isinstance(chunk_id_raw, str) and chunk_id_raw.strip():
                s = chunk_id_raw.strip()
                try:
                    chunk_id_val = int(s)
                except Exception:
                    chunk_id_val = s
            elif chunk_id_raw is not None:
                chunk_id_val = str(chunk_id_raw)

            doc_id_raw = c.get("document_id") if c.get("document_id") is not None else md.get("document_id")
            document_id_val: Any = -1
            if isinstance(doc_id_raw, int):
                document_id_val = doc_id_raw
            elif isinstance(doc_id_raw, str) and doc_id_raw.strip():
                s = doc_id_raw.strip()
                try:
                    document_id_val = int(s)
                except Exception:
                    document_id_val = s
            elif doc_id_raw is not None:
                document_id_val = str(doc_id_raw)

            document_name_val = (
                c.get("document_name")
                or md.get("display_name")
                or md.get("document_title")
                or md.get("filename")
                or "未知文档"
            )

            content_val = c.get("content") if c.get("content") is not None else ""
            if not isinstance(content_val, str):
                try:
                    content_val = str(content_val)
                except Exception:
                    content_val = ""

            page_raw = c.get("page_number")
            if page_raw is None:
                page_raw = md.get("page_number")
            page_val: Optional[int]
            if isinstance(page_raw, int):
                page_val = page_raw
            elif isinstance(page_raw, str):
                try:
                    page_val = int(page_raw)
                except Exception:
                    page_val = None
            else:
                page_val = None

            # Prefer already-normalized public score on the chunk first so
            # public_citations filtering is not undone by metadata fallbacks.
            rd = md.get("ranking_details") if isinstance(md.get("ranking_details"), dict) else {}
            candidates = [
                c.get("similarity_score"),
                md.get("vector_score"),
                c.get("vector_score"),
                rd.get("original_similarity") if rd else None,
            ]
            sim_val = 0.0
            for sim_raw in candidates:
                if sim_raw is None:
                    continue
                try:
                    v = float(sim_raw)
                except Exception:
                    continue
                if v < 0.0:
                    v = 0.0
                if v > 1.0:
                    # distance-like or oversized — normalize lightly
                    if v <= 2.0:
                        v = max(0.0, min(1.0, 1.0 - v)) if v > 1.0 else v
                    else:
                        v = max(0.0, min(1.0, 1.0 / (1.0 + v)))
                if v > 0.0:
                    sim_val = v
                    break
            else:
                sim_val = 0.0

            metadata_val = dict(md) if isinstance(md, dict) else {}
            if c.get("display_name") and "display_name" not in metadata_val:
                metadata_val["display_name"] = c.get("display_name")
            if not metadata_val:
                metadata_val = None

            normalized.append(
                RetrievedChunk(
                    chunk_id=chunk_id_val,
                    document_id=document_id_val,
                    document_name=document_name_val,
                    content=content_val,
                    page_number=page_val,
                    similarity_score=sim_val,
                    metadata=metadata_val,
                )
            )
        return normalized

    async def _get_chat_history(
        self,
        db: AsyncSession,
        session_id: Optional[str],
        limit: int = 10,
    ) -> str:
        """按会话获取最近若干轮用户/助理对话，拼接为简洁文本。

        - 仅在 session_id 存在时生效；否则返回空字符串。
        - 返回按时间升序的最近 N 条，格式："用户: ...\n助理: ..."，以便提示词引用。
        """
        try:
            if not session_id:
                return ""
            stmt = (
                select(QueryHistory)
                .where(QueryHistory.session_id == session_id)
                .order_by(QueryHistory.created_time.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            recent = result.scalars().all() or []
            # 反转为时间升序，便于阅读
            recent = list(reversed(recent))
            lines: List[str] = []
            for r in recent:
                q = (getattr(r, "query", None) or "").strip()
                a = (getattr(r, "response", None) or "").strip()
                if q:
                    lines.append(f"用户: {q}")
                if a:
                    lines.append(f"助理: {a}")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"获取会话历史失败：{e}")
            return ""
    

    def _normalize_sim(self, score: Any) -> float:
        try:
            s = float(score)
        except Exception:
            return 0.0
        if 0.0 <= s <= 1.0:
            return s
        if s > 1.0:
            if s <= 2.0:
                return max(0.0, min(1.0, 1.0 - s))
            return max(0.0, min(1.0, 1.0 / (1.0 + s)))
        return 0.0

    def _chunk_gate_score(self, c: Dict[str, Any]) -> float:
        """Score used by refusal gate: prefer cosine vector_score over RRF (~0.03)."""
        md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        rd = md.get("ranking_details") if isinstance(md.get("ranking_details"), dict) else {}
        # Prefer true cosine-like scores first; ignore tiny RRF unless nothing else.
        preferred = [
            rd.get("original_similarity"),
            md.get("vector_score"),
            c.get("vector_score"),
        ]
        best = 0.0
        for s in preferred:
            if s is None:
                continue
            best = max(best, self._normalize_sim(s))
        if best > 0:
            return best
        fallback = [
            c.get("similarity_score"),
            md.get("bm25_score"),
            rd.get("final_score"),
            md.get("rrf_score"),
        ]
        for s in fallback:
            if s is None:
                continue
            best = max(best, self._normalize_sim(s))
        return best

    def _best_similarity(self, chunks: List[Dict[str, Any]]) -> float:
        best = 0.0
        for c in chunks or []:
            try:
                best = max(best, self._chunk_gate_score(c))
            except Exception:
                continue
        return best

    def _refusal_answer(self, reason: str = "insufficient_evidence") -> str:
        if reason == "advice":
            return (
                "【结论】\n"
                "本系统不能给出是否购买保险、是否一定获赔的建议或承诺。\n\n"
                "【条款依据】\n"
                "演示语料仅用于说明犹豫期、等待期、责任免除等条款检索；"
                "真实核保与理赔取决于正式合同与事故事实。\n\n"
                "【不确定/边界】\n"
                "本系统不构成保险销售或理赔承诺。"
            )
        return (
            "【结论】\n"
            "未在已入库条款中找到充分依据，无法就该问题给出有引用支撑的结论。\n\n"
            "【条款依据】\n"
            "当前检索结果为空或相关度不足，请换用条款中的术语（如等待期、免赔额、责任免除）重试。\n\n"
            "【不确定/边界】\n"
            "本系统不构成保险销售或理赔承诺。"
        )

    def _is_advice_or_guarantee_question(self, question: str) -> bool:
        q = (question or "").strip()
        markers = [
            "一定能获赔",
            "保证获赔",
            "该不该买",
            "应不应该买",
            "推荐购买",
            "帮我配置",
            "今天买",
            "保证理赔",
        ]
        return any(m in q for m in markers)

    def _has_llm_credentials(self) -> bool:
        return bool((settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY or "").strip())

    def _is_off_topic(self, question: str, chunks: List[Dict[str, Any]]) -> bool:
        """Heuristic off-topic gate for demo corpus (weather / chit-chat)."""
        q = (question or "").strip()
        insurance_kw = [
            "保险", "条款", "等待期", "免赔", "责任免除", "犹豫期", "理赔", "保额",
            "身故", "重疾", "投保", "保单", "除外", "酒驾", "自杀",
        ]
        if any(k in q for k in insurance_kw):
            return False
        # non-insurance chit-chat markers
        chat_kw = ["天气", "北京", "上海", "你好", "讲个笑话", "股票", "足球"]
        if any(k in q for k in chat_kw):
            return True
        # weak overlap with top chunk text
        if not chunks:
            return True
        top = (chunks[0].get("content") or "")
        overlap = sum(1 for k in insurance_kw if k in top and k in q)
        return overlap == 0 and len(q) < 40 and not any(c in q for c in "等待免赔责任犹豫理赔保")


    async def process_query(
        self,
        db: AsyncSession,
        request: QueryRequest,
        stream: bool = False,
    ) -> Any:
        """处理查询请求，支持非流与SSE流（统一入口）。"""
        start_time = datetime.utcnow()

        # 统一：准备 Agent、LLM（轻量/核心）与可选查询重写
        agent = self.agent
        llm_core = LLMService.with_model(settings.OPENAI_MODEL_CORE)
        llm_light = LLMService.with_model(settings.OPENAI_MODEL_LIGHT)
        rewriter = QueryRewriterService(llm_service=llm_light)
        simple_mode = bool(getattr(settings, "SIMPLE_RAG_MODE", True))

        async def _rewrite_if_enabled(user_q: str) -> Dict[str, Any]:
            if not settings.ENABLE_QUERY_REWRITING:
                return {}
            try:
                chat_history = await self._get_chat_history(db, getattr(request, "session_id", None), limit=10)
                return await rewriter.rewrite_query(user_query=user_q, chat_history=chat_history)
            except Exception as e:
                logger.warning(f"查询重写失败，使用原始查询: {e}")
                return {}

        if not stream:
            try:
                # 强边界：购买/保证获赔类问题直接拒答（仍可检索展示）
                if self._is_advice_or_guarantee_question(request.question):
                    try:
                        ctx = await asyncio.wait_for(
                            agent.abuild_context(request.question),
                            timeout=getattr(settings, "CONTEXT_BUILD_TIMEOUT_SECS", 20),
                        )
                        retrieved_chunks = ctx.get("retrieved_chunks", []) or []
                        retrieved_chunks = self.curate_citations(
                            retrieved_chunks,
                            getattr(request, "question", "") or "",
                            limit=4,
                        )
                    except Exception:
                        retrieved_chunks = []
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    # advice: never attach sources (UI sticky / empty pane)
                    return QueryResponse(
                        question=request.question,
                        answer=self._refusal_answer("advice"),
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=0,
                        retrieved_chunks=[],
                        confidence_score=0.0,
                        query_id=None,
                        answer_kind="advice",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )

                rewrite_result = await _rewrite_if_enabled(request.question)
                # 使用独立查询作为检索输入
                question_for_retrieval = rewrite_result.get("independent_query") or request.question

                # 在构建上下文前调用路由器（R4.2）；SIMPLE 模式强制 RAG
                route_result = {"route": "RAG"}
                if (not simple_mode) and settings.ENABLE_QUERY_ROUTING:
                    router = QueryRouterService(llm_service=llm_light)
                    try:
                        route_result = await router.route_query(request.question)
                    except Exception as re:
                        logger.warning(f"查询路由失败，回退RAG: {re}")

                if (not simple_mode) and route_result.get("route") == "SQL":
                    # SQL 路径：执行只读查询并用 LLM 总结（R4.3）
                    t2s = TextToSQLService()
                    sql_query = route_result.get("query") or ""
                    try:
                        sql_rows = await t2s.aexecute_sql_query(db, sql_query)
                    except Exception as e:
                        logger.error(f"SQL 执行失败: {e}")
                        sql_rows = []

                    # 将结构化结果格式化为上下文字符串
                    try:
                        results_text = json.dumps(sql_rows, ensure_ascii=False)
                    except Exception:
                        results_text = str(sql_rows)

                    sql_context = [
                        {
                            "document_name": "SQL结果",
                            "page_number": "N/A",
                            "content": f"SQL: {sql_query}\n结果: {results_text}",
                        }
                    ]

                    gen_res = await llm_core.agenerate_response(
                        query=request.question,
                        context_chunks=sql_context,
                    )

                    answer_text = gen_res.get("answer", "")
                    response_time = (datetime.utcnow() - start_time).total_seconds()

                    response = QueryResponse(
                        question=request.question,
                        answer=answer_text,
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=0,
                        retrieved_chunks=[],
                        confidence_score=0.9,
                        query_id=None,
                        answer_kind="answer",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )

                    # 后台保存查询历史，避免阻塞主流程
                    try:
                        meta_payload = {
                            "route": "SQL",
                            "sql_query": sql_query,
                            "sql_result_count": len(sql_rows),
                        }
                        try:
                            if rewrite_result:
                                meta_payload.update({
                                    "primary_search_intent": rewrite_result.get("primary_search_intent"),
                                    "query_vectors": rewrite_result.get("query_vectors"),
                                    "micro_ontology": rewrite_result.get("micro_ontology"),
                                })
                        except Exception:
                            pass
                        rewriting_metadata_json = json.dumps(meta_payload, ensure_ascii=False)
                        asyncio.create_task(
                            self._save_query_history_bg(
                                question=request.question,
                                answer=answer_text,
                                query_type=request.query_type,
                                response_time=response_time,
                                chunks_used=0,
                                session_id=getattr(request, "session_id", None),
                                rewritten_query=(rewrite_result.get("independent_query") if rewrite_result else None),
                                rewriting_metadata_json=rewriting_metadata_json,
                                retrieved_chunks_json=None,
                            )
                        )
                    except Exception as save_error:
                        logger.debug(f"查询历史后台保存启动失败(SQL路径): {save_error}")

                    return response

                # 异步构建上下文（T3: asyncio.to_thread 包装同步I/O）
                try:
                    ctx = await asyncio.wait_for(
                        agent.abuild_context(question_for_retrieval),
                        timeout=getattr(settings, "CONTEXT_BUILD_TIMEOUT_SECS", 5),
                    )
                except asyncio.TimeoutError:
                    logger.warning("上下文构建超时，返回降级响应")
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    fallback = QueryResponse(
                        question=request.question,
                        answer="系统当前繁忙，检索上下文构建超时，请稍后重试。",
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=0,
                        retrieved_chunks=[],
                        confidence_score=0.0,
                        query_id=None,
                        answer_kind="degraded",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )
                    # 后台保存，不阻塞
                    try:
                        asyncio.create_task(
                            self._save_query_history_bg(
                                question=request.question,
                                answer=fallback.answer,
                                query_type=request.query_type,
                                response_time=response_time,
                                chunks_used=0,
                                session_id=getattr(request, "session_id", None),
                                rewritten_query=None,
                                rewriting_metadata_json=json.dumps({"route": "RAG", "degraded": True}, ensure_ascii=False),
                                retrieved_chunks_json=None,
                            )
                        )
                    except Exception:
                        pass
                    return fallback
                retrieved_chunks = ctx.get("retrieved_chunks", []) or []
                retrieved_chunks = self.curate_citations(
                    retrieved_chunks,
                    getattr(request, "question", "") or "",
                    limit=4,
                )
                rewritten_query = (
                    ctx.get("rewritten_query")
                    or (rewrite_result.get("independent_query") if rewrite_result else None)
                    or (question_for_retrieval if question_for_retrieval != request.question else None)
                )

                # 注入 KG 事实作为优先片段（仅 advanced）
                if not simple_mode:
                    try:
                        kg_service = KGService()
                        kg_facts = await kg_service.aget_facts(db, question_for_retrieval)
                        if kg_facts:
                            kg_chunk = {
                                "chunk_id": None,
                                "document_id": None,
                                "document_name": "知识图谱事实",
                                "content": "\n".join([f"- {f}" for f in kg_facts]),
                                "page_number": "N/A",
                                "similarity_score": 1.0,
                                "metadata": {"is_kg": True, "facts_count": len(kg_facts)},
                            }
                            retrieved_chunks = [kg_chunk] + retrieved_chunks
                    except Exception as kg_err:
                        logger.debug(f"KG事实注入失败：{kg_err}")

                # 拒答门闩：无检索 / 低分 / 明显离题
                best_sim = self._best_similarity(retrieved_chunks)
                off_topic = self._is_off_topic(request.question, retrieved_chunks)
                if off_topic or (not retrieved_chunks) or best_sim < float(getattr(settings, "SIMILARITY_THRESHOLD", 0.2)):
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    # Public API: no low-score filler citations on refusal
                    response = QueryResponse(
                        question=request.question,
                        answer=self._refusal_answer("insufficient_evidence"),
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=0,
                        retrieved_chunks=[],
                        confidence_score=round(best_sim, 4),
                        query_id=None,
                        answer_kind="refusal",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )
                    try:
                        asyncio.create_task(
                            self._save_query_history_bg(
                                question=request.question,
                                answer=response.answer,
                                query_type=request.query_type,
                                response_time=response_time,
                                chunks_used=0,
                                session_id=getattr(request, "session_id", None),
                                rewritten_query=rewritten_query,
                                rewriting_metadata_json=json.dumps(
                                    {
                                        "route": "RAG",
                                        "refused": True,
                                        "best_similarity": best_sim,
                                        "debug_chunk_count": len(retrieved_chunks or []),
                                    },
                                    ensure_ascii=False,
                                ),
                                # keep debug-only payload off public response; optional history
                                retrieved_chunks_json=None,
                            )
                        )
                    except Exception:
                        pass
                    return response

                # 无 API key：检索结果诚实降级
                if not self._has_llm_credentials():
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    preview_lines = []
                    for i, c in enumerate(retrieved_chunks[:3], 1):
                        name = c.get("document_name") or "未知文档"
                        page = c.get("page_number")
                        snippet = (c.get("content") or "")[:180].replace("\n", " ")
                        preview_lines.append(f"[{i}] {name} p.{page}: {snippet}")
                    answer_text = (
                        "【结论】\n"
                        "LLM 不可用（未配置 API Key），已返回检索片段摘要，未生成完整条款解释。\n\n"
                        "【条款依据】\n"
                        + ("\n".join(preview_lines) if preview_lines else "（无片段）")
                        + "\n\n【不确定/边界】\n本系统不构成保险销售或理赔承诺。"
                    )
                    return QueryResponse(
                        question=request.question,
                        answer=answer_text,
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=len(retrieved_chunks),
                        retrieved_chunks=self._to_retrieved_chunks(self.public_citations(retrieved_chunks)),
                        confidence_score=round(best_sim, 4),
                        query_id=None,
                        answer_kind="llm_unavailable",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )

                # 非流式：调用异步非流 LLM（T2）
                try:
                    gen_res = await asyncio.wait_for(
                        llm_core.agenerate_response(
                            query=request.question,
                            context_chunks=retrieved_chunks,
                        ),
                        timeout=getattr(settings, "LLM_ANSWER_TIMEOUT_SECS", 60),
                    )
                    if not gen_res.get("success", True):
                        preview = []
                        for i, c in enumerate(retrieved_chunks[:3], 1):
                            preview.append(
                                f"[{i}] {c.get('document_name')} p.{c.get('page_number')}: "
                                f"{(c.get('content') or '')[:120]}"
                            )
                        answer_text = (
                            "【结论】\nLLM 调用失败，以下为检索到的条款片段摘要。\n\n"
                            "【条款依据】\n"
                            + "\n".join(preview)
                            + "\n\n【不确定/边界】\n本系统不构成保险销售或理赔承诺。"
                        )
                        response_time = (datetime.utcnow() - start_time).total_seconds()
                        ui_chunks = self.citations_for_kind("llm_unavailable", retrieved_chunks)
                        return QueryResponse(
                            question=request.question,
                            answer=answer_text,
                            query_type=request.query_type,
                            response_time=response_time,
                            chunks_used=len(ui_chunks),
                            retrieved_chunks=self._to_retrieved_chunks(ui_chunks),
                            confidence_score=round(best_sim, 4),
                            query_id=None,
                            answer_kind="llm_unavailable",
                            embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                        )
                except asyncio.TimeoutError:

                    logger.warning("LLM生成超时，返回降级响应")
                    answer_text = "系统当前繁忙，生成答案超时，请稍后重试。"
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    response = QueryResponse(
                        question=request.question,
                        answer=answer_text,
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=0,
                        retrieved_chunks=[],
                        confidence_score=0.0,
                        query_id=None,
                        answer_kind="degraded",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )
                    # 后台保存，不阻塞
                    try:
                        rewriting_metadata_json = json.dumps({"route": "RAG", "degraded": True}, ensure_ascii=False)
                        asyncio.create_task(
                            self._save_query_history_bg(
                                question=request.question,
                                answer=answer_text,
                                query_type=request.query_type,
                                response_time=response_time,
                                chunks_used=len(retrieved_chunks),
                                session_id=getattr(request, "session_id", None),
                                rewritten_query=None,
                                rewriting_metadata_json=rewriting_metadata_json,
                                retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False) if retrieved_chunks else None,
                            )
                        )
                    except Exception:
                        pass
                    return response
                except TimeoutError:
                    logger.warning("LLM并发队列等待超时，返回降级响应")
                    answer_text = "系统当前繁忙，请稍后重试。"
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    response = QueryResponse(
                        question=request.question,
                        answer=answer_text,
                        query_type=request.query_type,
                        response_time=response_time,
                        chunks_used=0,
                        retrieved_chunks=[],
                        confidence_score=0.0,
                        query_id=None,
                        answer_kind="degraded",
                        embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                    )
                    # 后台保存，不阻塞
                    try:
                        rewriting_metadata_json = json.dumps({"route": "RAG", "degraded": True, "reason": "queue_timeout"}, ensure_ascii=False)
                        asyncio.create_task(
                            self._save_query_history_bg(
                                question=request.question,
                                answer=answer_text,
                                query_type=request.query_type,
                                response_time=response_time,
                                chunks_used=len(retrieved_chunks),
                                session_id=getattr(request, "session_id", None),
                                rewritten_query=None,
                                rewriting_metadata_json=rewriting_metadata_json,
                                retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False) if retrieved_chunks else None,
                            )
                        )
                    except Exception:
                        pass
                    return response

                answer_text = gen_res.get("answer", "")
                response_time = (datetime.utcnow() - start_time).total_seconds()

                ui_chunks = self.citations_for_kind("answer", retrieved_chunks)
                response = QueryResponse(
                    question=request.question,
                    answer=answer_text,
                    query_type=request.query_type,
                    response_time=response_time,
                    chunks_used=len(ui_chunks),
                    retrieved_chunks=self._to_retrieved_chunks(ui_chunks) if ui_chunks else [],
                    confidence_score=0.9,
                    query_id=None,
                    answer_kind="answer",
                    embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                )

                # 保存查询历史
                # 后台保存，不阻塞
                try:
                    meta_payload = {"route": "RAG"}
                    try:
                        if rewrite_result:
                            meta_payload.update({
                                "primary_search_intent": rewrite_result.get("primary_search_intent"),
                                "query_vectors": rewrite_result.get("query_vectors"),
                                "micro_ontology": rewrite_result.get("micro_ontology"),
                            })
                    except Exception:
                        pass
                    rewriting_metadata_json = json.dumps(meta_payload, ensure_ascii=False)
                    asyncio.create_task(
                        self._save_query_history_bg(
                            question=request.question,
                            answer=answer_text,
                            query_type=request.query_type,
                            response_time=response_time,
                            chunks_used=len(retrieved_chunks),
                            session_id=getattr(request, "session_id", None),
                            rewritten_query=rewritten_query,
                            rewriting_metadata_json=rewriting_metadata_json,
                            retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False) if retrieved_chunks else None,
                        )
                    )
                except Exception as save_error:
                    logger.debug(f"查询历史后台保存启动失败: {save_error}")

                return response
            except Exception as e:
                logger.error(f"非流式查询处理异常: {e}")
                response_time = (datetime.utcnow() - start_time).total_seconds()
                error_response = QueryResponse(
                    question=request.question,
                    answer="抱歉,处理您的查询时出现了错误,请稍后重试",
                    query_type=request.query_type,
                    response_time=response_time,
                    chunks_used=0,
                    retrieved_chunks=[],
                    confidence_score=0.0,
                    query_id=None,
                    answer_kind="degraded",
                    embedding_provider=getattr(getattr(self, "embedding_service", None), "provider", None),
                )
                try:
                    asyncio.create_task(
                        self._save_query_history_bg(
                            question=request.question,
                            answer=error_response.answer,
                            query_type=request.query_type,
                            response_time=response_time,
                            chunks_used=0,
                            session_id=getattr(request, "session_id", None),
                            rewritten_query=None,
                            rewriting_metadata_json=json.dumps({"route": "RAG"}, ensure_ascii=False),
                            retrieved_chunks_json=None,
                        )
                    )
                except Exception:
                    pass
                return error_response

        async def _sse_gen():
            try:
                rewrite_result = await _rewrite_if_enabled(request.question)
                question_for_retrieval = rewrite_result.get("independent_query") or request.question

                # 起始事件
                import json as _json
                start_evt = {
                    "type": "start",
                    "question": request.question,
                    "query_type": request.query_type,
                    "timestamp": start_time.timestamp(),
                }
                yield f"event: start\n"
                yield f"data: {_json.dumps(start_evt, ensure_ascii=False)}\n\n"

                # Early advice gate: no sources on purchase/guarantee questions
                if self._is_advice_or_guarantee_question(request.question):
                    advice_ans = self._refusal_answer("advice")
                    end_evt = {
                        "type": "end",
                        "answer": advice_ans,
                        "response_time": (datetime.utcnow() - start_time).total_seconds(),
                        "query_id": None,
                        "success": True,
                        "retrieved_chunks": [],
                        "chunks_used": 0,
                        "answer_kind": "advice",
                        "embedding_provider": getattr(getattr(self, "embedding_service", None), "provider", None),
                    }
                    yield f"event: end\n"
                    yield f"data: {_json.dumps(end_evt, ensure_ascii=False)}\n\n"
                    return

                # 在构建上下文前调用路由器（R4.2 - 流式路径），受开关控制
                route_result = {"route": "RAG"}
                if settings.ENABLE_QUERY_ROUTING:
                    router = QueryRouterService(llm_service=llm_light)
                    try:
                        route_result = await router.route_query(request.question)
                    except Exception as re:
                        logger.warning(f"流式查询路由失败，回退RAG: {re}")
                if route_result.get("route") == "SQL":
                    # SQL 路径：直接执行并总结，随后发送 end 事件
                    t2s = TextToSQLService()
                    sql_query = route_result.get("query") or ""
                    try:
                        sql_rows = await t2s.aexecute_sql_query(db, sql_query)
                    except Exception as e:
                        logger.error(f"SQL 执行失败(流式): {e}")
                        sql_rows = []

                    # 发送上下文事件，包含SQL元信息
                    ctx_evt = {
                        "type": "context",
                        "rewritten_query": (rewrite_result.get("independent_query") if rewrite_result else None),
                        "retrieved_chunks": [],
                        "route": "SQL",
                        "sql_query": sql_query,
                        "sql_result_count": len(sql_rows),
                    }
                    yield f"event: context\n"
                    yield f"data: {_json.dumps(ctx_evt, ensure_ascii=False)}\n\n"

                    # 总结结果
                    try:
                        results_text = _json.dumps(sql_rows, ensure_ascii=False)
                    except Exception:
                        results_text = str(sql_rows)
                    sql_context = [{"document_name": "SQL结果", "page_number": "N/A", "content": f"SQL: {sql_query}\n结果: {results_text}"}]
                    gen_res = await llm_core.agenerate_response(query=request.question, context_chunks=sql_context)
                    final_text = gen_res.get("answer", "")

                    # 保存历史
                    try:
                        meta_payload = {
                            "route": "SQL",
                            "sql_query": sql_query,
                            "sql_result_count": len(sql_rows),
                        }
                        if rewrite_result:
                            meta_payload.update({
                                "primary_search_intent": rewrite_result.get("primary_search_intent"),
                                "query_vectors": rewrite_result.get("query_vectors"),
                                "micro_ontology": rewrite_result.get("micro_ontology"),
                            })
                        rewriting_metadata_json = _json.dumps(meta_payload, ensure_ascii=False)
                        query_id = await self._save_query_history(
                            db,
                            request.question,
                            final_text.strip(),
                            request.query_type,
                            (datetime.utcnow() - start_time).total_seconds(),
                            0,
                            getattr(request, "session_id", None),
                            rewritten_query=(rewrite_result.get("independent_query") if rewrite_result else None),
                            rewriting_metadata_json=rewriting_metadata_json,
                            retrieved_chunks_json=None,
                        )
                    except Exception as save_error:
                        logger.warning(f"流式(SQL)查询历史保存失败: {save_error}")
                        query_id = None

                    end_evt = {
                        "type": "end",
                        "answer": final_text.strip(),
                        "response_time": (datetime.utcnow() - start_time).total_seconds(),
                        "query_id": query_id,
                        "success": True,
                    }
                    yield f"event: end\n"
                    yield f"data: {_json.dumps(end_evt, ensure_ascii=False)}\n\n"
                    return

                # 异步构建上下文
                ctx = await agent.abuild_context(question_for_retrieval)
                retrieved_chunks = ctx.get("retrieved_chunks", []) or []
                retrieved_chunks = self.curate_citations(
                    retrieved_chunks,
                    getattr(request, "question", "") or "",
                    limit=4,
                )
                rewritten_query = (
                    ctx.get("rewritten_query")
                    or (rewrite_result.get("independent_query") if rewrite_result else None)
                    or (question_for_retrieval if question_for_retrieval != request.question else None)
                )

                # 注入 KG 事实作为优先片段（SSE 路径）
                try:
                    kg_service = KGService()
                    kg_facts = await kg_service.aget_facts(db, question_for_retrieval)
                    if kg_facts:
                        kg_chunk = {
                            "chunk_id": None,
                            "document_id": None,
                            "document_name": "知识图谱事实",
                            "content": "\n".join([f"- {f}" for f in kg_facts]),
                            "page_number": "N/A",
                            "similarity_score": 1.0,
                            "metadata": {"is_kg": True, "facts_count": len(kg_facts)},
                        }
                        retrieved_chunks = [kg_chunk] + retrieved_chunks
                except Exception as kg_err:
                    logger.debug(f"KG事实注入失败(流式)：{kg_err}")

                # Refusal gate for SSE path (public chunks empty)
                best_sim = self._best_similarity(retrieved_chunks)
                off_topic = self._is_off_topic(request.question, retrieved_chunks)
                thr = float(getattr(settings, "SIMILARITY_THRESHOLD", 0.2))
                if off_topic or (not retrieved_chunks) or best_sim < thr:
                    refuse_ans = self._refusal_answer("insufficient_evidence")
                    end_evt = {
                        "type": "end",
                        "answer": refuse_ans,
                        "response_time": (datetime.utcnow() - start_time).total_seconds(),
                        "query_id": None,
                        "success": True,
                        "retrieved_chunks": [],
                        "chunks_used": 0,
                        "answer_kind": "refusal",
                        "confidence_score": round(best_sim, 4),
                        "embedding_provider": getattr(getattr(self, "embedding_service", None), "provider", None),
                    }
                    yield f"event: end\n"
                    yield f"data: {_json.dumps(end_evt, ensure_ascii=False)}\n\n"
                    return

                context_evt = {
                    "type": "context",
                    "rewritten_query": rewritten_query,
                    "retrieved_chunks": retrieved_chunks,
                    "route": "RAG",
                }
                yield f"event: context\n"
                yield f"data: {_json.dumps(context_evt, ensure_ascii=False)}\n\n"

                if not retrieved_chunks:
                    # 无上下文，直接返回错误并持久化
                    err_msg = "未检索到与问题相关的文档片段"
                    try:
                        await self._save_query_history(
                            db,
                            request.question,
                            err_msg,
                            request.query_type,
                            (datetime.utcnow() - start_time).total_seconds(),
                            0,
                            getattr(request, "session_id", None),
                            rewritten_query=rewritten_query,
                            rewriting_metadata_json=_json.dumps({"route": "RAG"}, ensure_ascii=False),
                            retrieved_chunks_json=None,
                        )
                    except Exception:
                        pass
                    err_evt = {"type": "error", "message": err_msg}
                    yield f"event: error\n"
                    yield f"data: {_json.dumps(err_evt, ensure_ascii=False)}\n\n"
                    return

                # 调用LLM流式生成：agenerate_stream 直接 yield 文本增量
                final_text = ""
                async for content in llm_core.agenerate_stream(
                    query=request.question,
                    context_chunks=retrieved_chunks,
                ):
                    try:
                        final_text += content
                        tok_evt = {"type": "token", "content": content}
                        yield f"event: token\n"
                        yield f"data: {_json.dumps(tok_evt, ensure_ascii=False)}\n\n"
                    except Exception:
                        # 忽略单次解析错误，继续流式
                        pass

                # 结束：保存历史并发送end事件
                try:
                    # 记录路由为 RAG，并合并重写元信息（若存在）
                    meta_payload = {"route": "RAG"}
                    try:
                        if rewrite_result:
                            meta_payload.update({
                                "primary_search_intent": rewrite_result.get("primary_search_intent"),
                                "query_vectors": rewrite_result.get("query_vectors"),
                                "micro_ontology": rewrite_result.get("micro_ontology"),
                            })
                    except Exception:
                        pass
                    rewriting_metadata_json = json.dumps(meta_payload, ensure_ascii=False)

                    query_id = await self._save_query_history(
                        db,
                        request.question,
                        final_text.strip() if final_text else "",
                        request.query_type,
                        (datetime.utcnow() - start_time).total_seconds(),
                        len(retrieved_chunks),
                        getattr(request, "session_id", None),
                        rewritten_query=rewritten_query,
                        rewriting_metadata_json=rewriting_metadata_json,
                        retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False),
                    )
                except Exception as save_error:
                    logger.warning(f"流式查询历史保存失败: {save_error}")
                    query_id = None

                _ans = final_text.strip() if final_text else ""
                _kind = "answer"
                _q = request.question or ""
                if "未在已入库条款中找到充分依据" in _ans:
                    _kind = "refusal"
                elif self._is_advice_or_guarantee_question(_q):
                    _kind = "advice"
                elif "LLM 不可用" in _ans:
                    _kind = "llm_unavailable"
                elif "系统当前繁忙" in _ans or "出现了错误" in _ans:
                    _kind = "degraded"
                ui_chunks = self.citations_for_kind(_kind, retrieved_chunks)
                try:
                    chunk_payload = [
                        rc.model_dump() if hasattr(rc, "model_dump") else dict(rc)
                        for rc in self._to_retrieved_chunks(ui_chunks)
                    ]
                except Exception:
                    chunk_payload = ui_chunks
                end_evt = {
                    "type": "end",
                    "answer": _ans,
                    "response_time": (datetime.utcnow() - start_time).total_seconds(),
                    "query_id": query_id,
                    "success": True,
                    "retrieved_chunks": chunk_payload,
                    "chunks_used": len(chunk_payload),
                    "answer_kind": _kind,
                    "embedding_provider": getattr(getattr(self, "embedding_service", None), "provider", None),
                }
                yield f"event: end\n"
                yield f"data: {_json.dumps(end_evt, ensure_ascii=False)}\n\n"

            except Exception as e:
                import json as _json3
                err_evt = {"type": "error", "message": str(e)}
                yield f"event: error\n"
                yield f"data: {_json3.dumps(err_evt, ensure_ascii=False)}\n\n"

        # 返回异步生成器（SSE字符串）
        return _sse_gen()

    async def stream_query(
        self,
        db: AsyncSession,
        request: QueryRequest,
    ) -> Any:
        """以事件流方式处理查询请求，逐步输出模型增量内容。

        事件序列：
        - {"type": "start", "question": ..., "query_type": ..., "timestamp": ...}
        - {"type": "context", "rewritten_query": ..., "retrieved_chunks": [...]}
        - {"type": "token", "content": "..."}  // 多次
        - {"type": "end", "answer": "...", "response_time": S, "query_id": N, "success": True}
        - 若失败：{"type": "error", "message": "..."}
        """
        start_time = datetime.utcnow()

        async def _gen():
            try:
                # 准备 Agent 与（可选）查询重写
                agent = self.agent
                llm_core = LLMService.with_model(settings.OPENAI_MODEL_CORE)
                llm_light = LLMService.with_model(settings.OPENAI_MODEL_LIGHT)
                rewriter = QueryRewriterService(llm_service=llm_light)
                question_for_retrieval = request.question
                rewrite_result: Dict[str, Any] = {}
                if settings.ENABLE_QUERY_REWRITING:
                    try:
                        chat_history = await self._get_chat_history(db, getattr(request, "session_id", None), limit=10)
                        rewrite_result = await rewriter.rewrite_query(user_query=request.question, chat_history=chat_history)
                        independent_q = rewrite_result.get("independent_query")
                        if independent_q:
                            question_for_retrieval = independent_q
                    except Exception as e:
                        logger.warning(f"流式查询重写失败，回退原始查询: {e}")

                # 起始事件
                yield {
                    "type": "start",
                    "question": request.question,
                    "query_type": request.query_type,
                    "timestamp": start_time.timestamp(),
                }

                if self._is_advice_or_guarantee_question(request.question):
                    yield {
                        "type": "end",
                        "answer": self._refusal_answer("advice"),
                        "response_time": (datetime.utcnow() - start_time).total_seconds(),
                        "query_id": None,
                        "success": True,
                        "retrieved_chunks": [],
                        "chunks_used": 0,
                        "answer_kind": "advice",
                        "embedding_provider": getattr(getattr(self, "embedding_service", None), "provider", None),
                    }
                    return

                # 构建上下文（RAG前四步）
                ctx = agent.build_context(question_for_retrieval)
                retrieved_chunks = ctx.get("retrieved_chunks", []) or []
                retrieved_chunks = self.curate_citations(
                    retrieved_chunks,
                    getattr(request, "question", "") or "",
                    limit=4,
                )
                rewritten_query = (
                    ctx.get("rewritten_query")
                    or (rewrite_result.get("independent_query") if rewrite_result else None)
                    or (question_for_retrieval if question_for_retrieval != request.question else None)
                )

                # Public context: drop zero-score fillers; refuse if weak/off-topic
                best_sim = self._best_similarity(retrieved_chunks)
                off_topic = self._is_off_topic(request.question, retrieved_chunks)
                thr = float(getattr(settings, "SIMILARITY_THRESHOLD", 0.2))
                if off_topic or (not retrieved_chunks) or best_sim < thr:
                    yield {
                        "type": "end",
                        "answer": self._refusal_answer("insufficient_evidence"),
                        "response_time": (datetime.utcnow() - start_time).total_seconds(),
                        "query_id": None,
                        "success": True,
                        "retrieved_chunks": [],
                        "chunks_used": 0,
                        "answer_kind": "refusal",
                        "confidence_score": round(best_sim, 4),
                        "embedding_provider": getattr(getattr(self, "embedding_service", None), "provider", None),
                    }
                    return

                pub_ctx = self.public_citations(retrieved_chunks)
                yield {
                    "type": "context",
                    "rewritten_query": rewritten_query,
                    "retrieved_chunks": pub_ctx,
                    "route": "RAG",
                }

                if not retrieved_chunks:
                    # 无上下文，直接返回错误并持久化错误历史
                    error_msg = "未检索到与问题相关的文档片段"
                    response_time = (datetime.utcnow() - start_time).total_seconds()
                    try:
                        await self._save_query_history(
                            db,
                            request.question,
                            error_msg,
                            request.query_type,
                            response_time,
                            0,
                            getattr(request, "session_id", None),
                            rewritten_query=rewritten_query,
                            rewriting_metadata_json=json.dumps({"route": "RAG"}, ensure_ascii=False),
                            retrieved_chunks_json=None,
                        )
                    except Exception:
                        pass
                    yield {"type": "error", "message": error_msg}
                    return

                # 进行流式生成（仅透传 token 事件；end 事件统一由此方法发送）
                final_text = ""
                tokens_used = 0
                response_time = 0.0
                async for ev in llm_core.stream_answer(request.question, retrieved_chunks):
                    etype = ev.get("type")
                    if etype == "token":
                        final_text += ev.get("content", "")
                        yield ev
                    elif etype == "end":
                        tokens_used = int(ev.get("tokens_used", 0) or 0)
                        response_time = float(ev.get("response_time", 0.0) or 0.0)
                    elif etype == "error":
                        # 输出错误并保存历史
                        err_msg = ev.get("message") or "流式生成失败"
                        response_time = float(ev.get("response_time", 0.0) or 0.0)
                        try:
                            await self._save_query_history(
                                db,
                                request.question,
                                err_msg,
                                request.query_type,
                                response_time,
                                len(retrieved_chunks),
                                rewritten_query=rewritten_query,
                                rewriting_metadata_json=json.dumps({"route": "RAG"}, ensure_ascii=False),
                                retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False),
                            )
                        except Exception:
                            pass
                        yield {"type": "error", "message": err_msg}
                        return

                # 保存成功历史并发送最终 end 事件
                try:
                    # 记录路由为 RAG，并合并重写元数据（若存在）
                    meta_payload = {"route": "RAG"}
                    try:
                        if rewrite_result:
                            meta_payload.update({
                                "primary_search_intent": rewrite_result.get("primary_search_intent"),
                                "query_vectors": rewrite_result.get("query_vectors"),
                                "micro_ontology": rewrite_result.get("micro_ontology"),
                            })
                    except Exception:
                        pass
                    rewriting_metadata_json = json.dumps(meta_payload, ensure_ascii=False)

                    query_id = await self._save_query_history(
                        db,
                        request.question,
                        final_text.strip() if final_text else "",
                        request.query_type,
                        response_time if response_time else (datetime.utcnow() - start_time).total_seconds(),
                        len(retrieved_chunks),
                        getattr(request, "session_id", None),
                        rewritten_query=rewritten_query,
                        rewriting_metadata_json=rewriting_metadata_json,
                        retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False),
                    )
                except Exception as save_error:
                    logger.warning(f"流式查询历史保存失败: {save_error}")
                    query_id = None

                # Classify stream end for UI state cards
                _ans = final_text.strip() if final_text else ""
                _kind = "answer"
                _q = request.question or ""
                if "未在已入库条款中找到充分依据" in _ans:
                    _kind = "refusal"
                elif self._is_advice_or_guarantee_question(_q):
                    _kind = "advice"
                elif "LLM 不可用" in _ans:
                    _kind = "llm_unavailable"
                elif "系统当前繁忙" in _ans or "出现了错误" in _ans:
                    _kind = "degraded"
                ui_chunks = self.citations_for_kind(_kind, retrieved_chunks)
                try:
                    chunk_payload = [
                        rc.model_dump() if hasattr(rc, "model_dump") else dict(rc)
                        for rc in self._to_retrieved_chunks(ui_chunks)
                    ]
                except Exception:
                    chunk_payload = ui_chunks
                yield {
                    "type": "end",
                    "answer": _ans,
                    "response_time": response_time if response_time else (datetime.utcnow() - start_time).total_seconds(),
                    "query_id": query_id,
                    "success": True,
                    "retrieved_chunks": chunk_payload,
                    "chunks_used": len(chunk_payload),
                    "answer_kind": _kind,
                    "embedding_provider": getattr(getattr(self, "embedding_service", None), "provider", None),
                }

            except Exception as e:
                logger.error(f"流式查询处理异常: {e}")
                yield {"type": "error", "message": str(e)}

        # 返回异步生成器
        return _gen()

    async def _save_query_history(
        self,
        db: AsyncSession,
        question: str,
        answer: str,
        query_type: str,
        response_time: float,
        chunks_used: int,
        session_id: Optional[str] = None,
        rewritten_query: Optional[str] = None,
        rewriting_metadata_json: Optional[str] = None,
        retrieved_chunks_json: Optional[str] = None
    ) -> Optional[int]:
        """保存查询历史"""
        try:
            # 确保数据库存在重写相关列（无迁移环境下的轻量DDL，SQLite 适配）
            try:
                pragma = await db.execute(text("PRAGMA table_info('query_history')"))
                rows = pragma.all()
                cols = {row[1] if len(row) > 1 else (row.get('name') if isinstance(row, dict) else None) for row in rows}
                cols = {c for c in cols if c}
                alter_sqls = []
                if 'session_id' not in cols:
                    alter_sqls.append("ALTER TABLE query_history ADD COLUMN session_id TEXT")
                if 'rewritten_query' not in cols:
                    alter_sqls.append("ALTER TABLE query_history ADD COLUMN rewritten_query TEXT")
                if 'rewriting_metadata_json' not in cols:
                    alter_sqls.append("ALTER TABLE query_history ADD COLUMN rewriting_metadata_json TEXT")
                if 'retrieved_chunks' not in cols:
                    alter_sqls.append("ALTER TABLE query_history ADD COLUMN retrieved_chunks TEXT")
                for sql in alter_sqls:
                    await db.execute(text(sql))
                if alter_sqls:
                    await db.commit()
            except Exception:
                # 若检查或DDL失败，不影响后续保存（可能是首次建表或权限限制）
                try:
                    await db.rollback()
                except Exception:
                    pass

            # 创建查询历史记录
            query_history = QueryHistory(
                query=question,
                response=answer,
                model_used=query_type,
                response_time=response_time,
                retrieved_chunks=retrieved_chunks_json,
                tokens_used=None,
                cost=None,
                rating=None,
                feedback=None,
                session_id=session_id,
                rewritten_query=rewritten_query,
                rewriting_metadata_json=rewriting_metadata_json
            )
            
            db.add(query_history)
            await db.commit()
            await db.refresh(query_history)
            
            logger.info(f"查询历史保存成功,ID: {query_history.id}")
            return query_history.id
            
        except Exception as e:
            logger.error(f"保存查询历史失败: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return None

    async def _save_query_history_bg(
        self,
        question: str,
        answer: str,
        query_type: str,
        response_time: float,
        chunks_used: int,
        session_id: Optional[str] = None,
        rewritten_query: Optional[str] = None,
        rewriting_metadata_json: Optional[str] = None,
        retrieved_chunks_json: Optional[str] = None,
    ) -> None:
        """后台保存查询历史：自行创建/关闭会话，避免阻塞主请求。"""
        try:
            async with db_manager.SessionLocal() as session:
                await self._save_query_history(
                    db=session,
                    question=question,
                    answer=answer,
                    query_type=query_type,
                    response_time=response_time,
                    chunks_used=chunks_used,
                    session_id=session_id,
                    rewritten_query=rewritten_query,
                    rewriting_metadata_json=rewriting_metadata_json,
                    retrieved_chunks_json=retrieved_chunks_json,
                )
        except Exception as e:
            logger.debug(f"后台保存查询历史失败: {e}")

    async def get_query_history(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50,
        query_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[QueryHistory]:
        """获取查询历史"""
        try:
            stmt = select(QueryHistory)

            # 数据库模型使用 model_used 作为查询类型字段
            if query_type:
                stmt = stmt.where(QueryHistory.model_used == query_type)

            # 统一使用 created_time 字段进行时间过滤
            if start_date:
                stmt = stmt.where(QueryHistory.created_time >= start_date)

            if end_date:
                stmt = stmt.where(QueryHistory.created_time <= end_date)

            stmt = stmt.order_by(QueryHistory.created_time.desc()).offset(skip).limit(limit)
            result = await db.execute(stmt)
            history = result.scalars().all()

            logger.info(f"获取查询历史成功,共 {len(history)} 条记录")
            return history

        except Exception as e:
            logger.error(f"获取查询历史失败: {e}")
            return []

    async def update_query_feedback(
        self,
        db: AsyncSession,
        query_id: int,
        rating: int,
        comment: Optional[str] = None
    ) -> bool:
        """更新查询反馈"""
        try:
            result = await db.execute(select(QueryHistory).where(QueryHistory.id == query_id))
            query_history = result.scalar_one_or_none()

            if not query_history:
                logger.warning(f"查询记录不存在: {query_id}")
                return False

            # 与数据库模型字段对齐
            query_history.rating = rating
            query_history.feedback = comment
            await db.commit()

            logger.info(f"查询反馈更新成功: query_id={query_id}, rating={rating}")
            return True

        except Exception as e:
            logger.error(f"更新查询反馈失败: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return False

    async def get_query_statistics(self, db: AsyncSession, days: int = 30) -> QueryStatistics:
        """获取查询统计信息"""
        try:
            from datetime import timedelta

            # 计算时间范围
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # 总查询数
            total_queries = (
                await db.execute(
                    select(func.count()).select_from(QueryHistory).where(
                        QueryHistory.created_time >= start_date
                    )
                )
            ).scalar() or 0

            # 平均响应时间
            avg_response_time = (
                await db.execute(
                    select(func.avg(QueryHistory.response_time)).where(
                        QueryHistory.created_time >= start_date
                    )
                )
            ).scalar() or 0

            # 平均评分
            avg_rating = (
                await db.execute(
                    select(func.avg(QueryHistory.rating)).where(
                        QueryHistory.rating.isnot(None),
                        QueryHistory.created_time >= start_date,
                    )
                )
            ).scalar() or 0

            # 今日查询数
            today = datetime.utcnow().date()
            today_queries = (
                await db.execute(
                    select(func.count()).select_from(QueryHistory).where(
                        func.date(QueryHistory.created_time) == today
                    )
                )
            ).scalar() or 0

            # 查询类型分布 - 由于数据库模型中没有query_type字段,使用model_used代替
            type_stmt = (
                select(
                    QueryHistory.model_used,
                    func.count(QueryHistory.model_used).label('count')
                )
                .where(QueryHistory.created_time >= start_date)
                .group_by(QueryHistory.model_used)
            )
            type_result = await db.execute(type_stmt)
            query_type_stats = type_result.all()

            query_type_distribution = {stat[0]: stat[1] for stat in query_type_stats}

            stats = QueryStatistics(
                total_queries=total_queries,
                avg_response_time=round(avg_response_time, 3),
                avg_rating=round(avg_rating, 2),
                today_queries=today_queries,
                query_type_distribution=query_type_distribution,
                period_days=days,
                avg_chunks_used=0.0,  # 添加缺失字段
                avg_confidence_score=0.0,  # 添加缺失字段
                feedback_stats={}  # 添加缺失字段
            )

            logger.info("查询统计信息获取成功")
            return stats

        except Exception as e:
            logger.error(f"获取查询统计信息失败: {e}")
            return QueryStatistics(
                total_queries=0,
                avg_response_time=0,
                avg_rating=0,
                today_queries=0,
                query_type_distribution={},
                period_days=days,
                avg_chunks_used=0.0,  # 添加缺失字段
                avg_confidence_score=0.0,  # 添加缺失字段
                feedback_stats={}  # 添加缺失字段
            )


@lru_cache(maxsize=1)
def _load_ontology() -> dict:
    """加载保险术语本体库JSON，使用缓存减少I/O。"""
    try:
        with open(settings.ONTOLOGY_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载本体库失败，使用空本体：{e}")
        return {
            "synonyms": {},
            "product_types": [],
            "coverage_terms": [],
            "claim_terms": [],
            "exclusions": [],
        }
