"""
查询服务
整合向量搜索和LLM生成,提供完整的问答功能
"""

from datetime import datetime
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
from app.services.llm_service import LLMService
from app.services.query_rewriter_service import QueryRewriterService
from app.services.query_router_service import QueryRouterService
from app.services.text_to_sql_service import TextToSQLService

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

    def _to_retrieved_chunks(self, chunks: List[Dict[str, Any]]) -> List[RetrievedChunk]:
        """将原始检索块字典安全规范化为 RetrievedChunk 模型，避免 None/类型不匹配引发验证错误。

        兼容不同来源的元数据：
        - 缺失的 `chunk_id`/`document_id` 以 -1 兜底；字符串形式尝试转换为 int。
        - `document_name` 优先使用字典字段，其次回退到元数据中的 `document_title`/`filename`。
        - `page_number` 尝试转为 int，失败则置为 None。
        - `similarity_score` 优先使用字段值，其次回退到 `ranking_details.original_similarity` 或置 0.0。
        - `metadata` 保留为原始字典（如非字典则置为 None）。
        """
        normalized: List[RetrievedChunk] = []
        for c in chunks or []:
            md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}

            # chunk_id
            chunk_id_raw = c.get("chunk_id")
            chunk_id_val: int
            if isinstance(chunk_id_raw, int):
                chunk_id_val = chunk_id_raw
            elif isinstance(chunk_id_raw, str):
                try:
                    chunk_id_val = int(chunk_id_raw)
                except Exception:
                    chunk_id_val = -1
            else:
                chunk_id_val = -1

            # document_id
            doc_id_raw = c.get("document_id")
            document_id_val: int
            if isinstance(doc_id_raw, int):
                document_id_val = doc_id_raw
            elif isinstance(doc_id_raw, str):
                try:
                    document_id_val = int(doc_id_raw)
                except Exception:
                    document_id_val = -1
            else:
                document_id_val = -1

            # document_name
            document_name_val = (
                c.get("document_name")
                or md.get("document_title")
                or md.get("filename")
                or "未知文档"
            )

            # content
            content_val = c.get("content") if c.get("content") is not None else ""
            if not isinstance(content_val, str):
                try:
                    content_val = str(content_val)
                except Exception:
                    content_val = ""

            # page_number
            page_raw = c.get("page_number")
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

            # similarity_score
            sim_raw = c.get("similarity_score")
            if sim_raw is None:
                rd = md.get("ranking_details") if isinstance(md.get("ranking_details"), dict) else {}
                sim_raw = rd.get("original_similarity") if rd else None
            try:
                sim_val = float(sim_raw) if sim_raw is not None else 0.0
            except Exception:
                sim_val = 0.0
            # 夹逼到 [0, 1]
            if sim_val < 0.0:
                sim_val = 0.0
            if sim_val > 1.0:
                sim_val = 1.0

            # metadata
            metadata_val = md if isinstance(md, dict) else None

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
    
    async def process_query(
        self,
        db: AsyncSession,
        request: QueryRequest,
        stream: bool = False,
    ) -> Any:
        """处理查询请求，支持非流与SSE流（统一入口）。"""
        start_time = datetime.utcnow()

        # 统一：准备 Agent、LLM 与可选查询重写
        agent = self.agent
        llm = LLMService()
        rewriter = QueryRewriterService(llm_service=llm)

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
                rewrite_result = await _rewrite_if_enabled(request.question)
                # 使用独立查询作为检索输入
                question_for_retrieval = rewrite_result.get("independent_query") or request.question

                # 在构建上下文前调用路由器（R4.2）
                router = QueryRouterService(llm_service=llm)
                route_result = await router.route_query(request.question)

                if route_result.get("route") == "SQL":
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

                    gen_res = await llm.agenerate_response(
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
                    )

                    # 保存查询历史（记录路由与SQL）
                    try:
                        rewriting_metadata_json = None
                        meta_payload = {
                            "route": "SQL",
                            "sql_query": sql_query,
                            "sql_result_count": len(sql_rows),
                        }
                        try:
                            # 合并重写元数据（若存在）
                            if rewrite_result:
                                meta_payload.update({
                                    "primary_search_intent": rewrite_result.get("primary_search_intent"),
                                    "query_vectors": rewrite_result.get("query_vectors"),
                                    "micro_ontology": rewrite_result.get("micro_ontology"),
                                })
                            rewriting_metadata_json = json.dumps(meta_payload, ensure_ascii=False)
                        except Exception:
                            rewriting_metadata_json = json.dumps({"route": "SQL", "sql_query": sql_query}, ensure_ascii=False)

                        query_id = await self._save_query_history(
                            db,
                            request.question,
                            answer_text,
                            request.query_type,
                            response_time,
                            0,
                            getattr(request, "session_id", None),
                            rewritten_query=(rewrite_result.get("independent_query") if rewrite_result else None),
                            rewriting_metadata_json=rewriting_metadata_json,
                            retrieved_chunks_json=None,
                        )
                        response.query_id = query_id
                    except Exception as save_error:
                        logger.warning(f"查询历史保存失败(SQL路径): {save_error}")

                    return response

                # 异步构建上下文（T3: asyncio.to_thread 包装同步I/O）
                ctx = await agent.abuild_context(question_for_retrieval)
                retrieved_chunks = ctx.get("retrieved_chunks", []) or []
                rewritten_query = (
                    ctx.get("rewritten_query")
                    or (rewrite_result.get("independent_query") if rewrite_result else None)
                    or (question_for_retrieval if question_for_retrieval != request.question else None)
                )

                # 非流式：调用异步非流 LLM（T2）
                gen_res = await llm.agenerate_response(
                    query=request.question,
                    context_chunks=retrieved_chunks,
                )

                answer_text = gen_res.get("answer", "")
                response_time = (datetime.utcnow() - start_time).total_seconds()

                response = QueryResponse(
                    question=request.question,
                    answer=answer_text,
                    query_type=request.query_type,
                    response_time=response_time,
                    chunks_used=len(retrieved_chunks),
                    retrieved_chunks=self._to_retrieved_chunks(retrieved_chunks) if retrieved_chunks else [],
                    confidence_score=0.9,
                    query_id=None,
                )

                # 保存查询历史
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
                        # 忽略重写元数据合并错误
                        pass
                    rewriting_metadata_json = json.dumps(meta_payload, ensure_ascii=False)

                    query_id = await self._save_query_history(
                        db,
                        request.question,
                        answer_text,
                        request.query_type,
                        response_time,
                        len(retrieved_chunks),
                        getattr(request, "session_id", None),
                        rewritten_query=rewritten_query,
                        rewriting_metadata_json=rewriting_metadata_json,
                        retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False) if retrieved_chunks else None,
                    )
                    response.query_id = query_id
                except Exception as save_error:
                    logger.warning(f"查询历史保存失败: {save_error}")

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
                )
                try:
                    query_id = await self._save_query_history(
                        db,
                        request.question,
                        error_response.answer,
                        request.query_type,
                        response_time,
                        0,
                        getattr(request, "session_id", None),
                        rewritten_query=None,
                        rewriting_metadata_json=json.dumps({"route": "RAG"}, ensure_ascii=False),
                        retrieved_chunks_json=None,
                    )
                    error_response.query_id = query_id
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

                # 在构建上下文前调用路由器（R4.2 - 流式路径）
                router = QueryRouterService(llm_service=llm)
                route_result = await router.route_query(request.question)
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
                    gen_res = await llm.agenerate_response(query=request.question, context_chunks=sql_context)
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
                rewritten_query = (
                    ctx.get("rewritten_query")
                    or (rewrite_result.get("independent_query") if rewrite_result else None)
                    or (question_for_retrieval if question_for_retrieval != request.question else None)
                )

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
                async for content in llm.agenerate_stream(
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

                end_evt = {
                    "type": "end",
                    "answer": final_text.strip() if final_text else "",
                    "response_time": (datetime.utcnow() - start_time).total_seconds(),
                    "query_id": query_id,
                    "success": True,
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
                llm = LLMService()
                rewriter = QueryRewriterService(llm_service=llm)
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

                # 构建上下文（RAG前四步）
                ctx = agent.build_context(question_for_retrieval)
                retrieved_chunks = ctx.get("retrieved_chunks", []) or []
                rewritten_query = (
                    ctx.get("rewritten_query")
                    or (rewrite_result.get("independent_query") if rewrite_result else None)
                    or (question_for_retrieval if question_for_retrieval != request.question else None)
                )

                yield {
                    "type": "context",
                    "rewritten_query": rewritten_query,
                    "retrieved_chunks": retrieved_chunks,
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
                async for ev in llm.stream_answer(request.question, retrieved_chunks):
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

                yield {
                    "type": "end",
                    "answer": final_text.strip() if final_text else "",
                    "response_time": response_time if response_time else (datetime.utcnow() - start_time).total_seconds(),
                    "query_id": query_id,
                    "success": True,
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
