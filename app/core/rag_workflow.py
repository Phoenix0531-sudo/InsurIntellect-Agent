#!/usr/bin/env python3
"""
InsurIntellect Agent - RAG Workflow Engine
=========================================

This module implements the core RAG (Retrieval-Augmented Generation) workflow
for the InsurIntellect Agent. It orchestrates a multi-stage AI collaboration
process from receiving user queries to generating final answers.

The workflow consists of:
1. Query Architect: Rewrites and optimizes user queries
2. Document Retrieval: Searches the vector database for relevant content
3. Lead Reviewer: Filters and selects the most relevant document chunks
4. Report Author: Generates comprehensive answers based on selected context

Author: InsurIntellect Agent Development Team
Version: 1.0.0
"""

import os
import json
import logging
from app.core.app_logging import get_logger as app_get_logger
import numpy as np
from typing import Dict, List, Any, Tuple
from datetime import datetime
import asyncio

# 在导入langchain之前设置环境变量（OpenAI-compatible；兼容 siliconflow 回退）
from app.core.config import settings
_api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY or ""
_base_url = settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL or ""
if _api_key:
    os.environ["OPENAI_API_KEY"] = _api_key
if _base_url:
    os.environ["OPENAI_BASE_URL"] = _base_url

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_chroma import Chroma
# 新增导入：用于构建提示与解析输出（AI判别辅助）
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import ValidationError
from app.models.schemas import RegulatoryCheck, QueryIntent

# 导入应用配置和提示模板
from app.prompts import (
    QUERY_ARCHITECT_PROMPT,
    LEAD_REVIEWER_PROMPT,
    REPORT_AUTHOR_PROMPT
)
from app.core.timeliness import compute_timeliness_score
from app.core.fusion import reciprocal_rank_fusion
import jieba
from app.services.embedding_service import EmbeddingService
from app.services.query_intent_service import QueryIntentService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



def _normalize_vector_score(score: float) -> float:
    """Map raw vector score/distance into roughly [0,1] cosine-like similarity."""
    try:
        s = float(score)
    except Exception:
        return 0.0
    if 0.0 <= s <= 1.0:
        return s
    # LangChain/Chroma may return distance (lower better). Cosine distance often in [0, 2].
    if s > 1.0:
        if s <= 2.0:
            return max(0.0, min(1.0, 1.0 - s))
        return max(0.0, min(1.0, 1.0 / (1.0 + s)))
    # negative unexpected
    return 0.0


class InsurIntellectAgent:
    """
    InsurIntellect智能代理核心类
    
    封装从接收用户问题到生成最终答案的多阶段 AI 协作工作流。
    通过查询架构师、文档检索、首席评审员和报告撰写人的协作，
    提供高质量的保险领域智能问答服务。
    """
    
    def __init__(self):
        """
        初始化InsurIntellect智能代理
        
        初始化组件:
        - ChatOpenAI LLM实例
        - OpenAI嵌入模型
        - ChromaDB向量数据库检索器
        """
        logger.info("正在初始化InsurIntellect智能代理...")
        
        try:
            # 初始化 ChatOpenAI（OpenAI-compatible；兼容 siliconflow 回退）
            _model = (
                settings.OPENAI_MODEL_CORE
                or settings.OPENAI_MODEL
                or settings.SILICONFLOW_MODEL
                or "gpt-5.4"
            )
            _api_key = (settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY or "").strip()
            _base_url = (settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL or "").strip() or None
            self.llm = None
            if _api_key:
                self.llm = ChatOpenAI(
                    model=_model,
                    temperature=settings.OPENAI_TEMPERATURE,
                    max_tokens=settings.OPENAI_MAX_TOKENS,
                    api_key=_api_key,
                    base_url=_base_url,
                )
                logger.info("ChatOpenAI LLM初始化成功")
            else:
                logger.warning("未配置 API Key：跳过 ChatOpenAI 初始化（检索仍可用，生成走 llm_unavailable）")
            
            # 初始化嵌入服务（双模式）
            self.embedding_service = EmbeddingService(model_name=settings.OPENAI_EMBEDDING_MODEL)
            self.embeddings = self.embedding_service.embedding_function
            logger.info("嵌入服务初始化成功（双模式）")
            # 额外记录到应用主日志记录器，确保写入 logs/app.log
            try:
                app_get_logger("insurintellect").info("嵌入服务初始化成功（双模式）")
            except Exception:
                pass
            # 意图分类服务（KCP-FIX-4）
            try:
                self.intent_service = QueryIntentService()
            except Exception:
                self.intent_service = None
            
            # 初始化向量数据库
            try:
                from app.core.chromadb_manager import chroma_manager
                
                # 使用单例管理器获取ChromaDB客户端
                chroma_client = chroma_manager.get_client()
                
                self.vectorstore = Chroma(
                    client=chroma_client,
                    collection_name="insurance_documents",
                    embedding_function=self.embeddings,
                    persist_directory=settings.CHROMA_PERSIST_DIRECTORY
                )
                
                logger.info("向量数据库初始化完成: chroma（使用单例管理器）")
                
            except Exception as e:
                logger.exception("向量数据库初始化失败")
                raise
            
            # 创建检索器，设置初步检索数量
            self.retriever = self.vectorstore.as_retriever(
                search_kwargs={"k": settings.MAX_RETRIEVED_CHUNKS * 2}  # 初步检索更多文档供后续筛选
            )
            logger.info(f"ChromaDB检索器初始化成功,检索路径: {settings.CHROMA_PERSIST_DIRECTORY}")

            # BM25 资源占位
            self.bm25_index = None
            self.bm25_chunk_map = {}
            self.bm25_available = False

            # 新增：加载并缓存监管文件，以便快速访问和后续AI判断参考
            # 说明：优先使用向量库检索器的 get 能力，失败时回退到底层 Chroma collection
            logger.info("正在加载并缓存监管文件...")
            try:
                # 假设数据库中，监管文件的元数据 document_type 被标记为 '监管文件'
                self.regulatory_docs = self.retriever.vectorstore.get(
                    where={"document_type": "监管文件"},
                    include=["metadatas", "documents"]
                )
                count = len(self.regulatory_docs.get("documents", []) or [])
                logger.info(f"已缓存 {count} 份监管文件。")
            except Exception as e:
                logger.warning(f"通过检索器缓存监管文件失败，尝试底层collection: {e}")
                try:
                    # 回退到底层 chroma collection
                    self.regulatory_docs = self.vectorstore._collection.get(
                        where={"document_type": "监管文件"},
                        include=["metadatas", "documents"]
                    )
                    count = len(self.regulatory_docs.get("documents", []) or [])
                    logger.info(f"已缓存 {count} 份监管文件（底层collection）。")
                except Exception as e2:
                    logger.warning(f"缓存监管文件失败: {e2}")
                    self.regulatory_docs = {}

            # 最近一次运行的检索与排序详情（用于审计与持久化）
            self.last_run: Dict[str, Any] = {}

        except Exception as e:
            logger.exception("初始化InsurIntellect智能代理失败")
            raise
    
    def run_query_architect(self, user_query: str) -> Dict[str, Any]:
        """
        运行查询架构师：重写和优化用户查询
        
        Args:
            user_query (str): 用户原始查询
            
        Returns:
            Dict[str, Any]: 包含重写后查询的字典
        """
        try:
            logger.info("查询架构师开始工作...")
            
            # 使用QUERY_ARCHITECT_PROMPT模板
            prompt = QUERY_ARCHITECT_PROMPT.format(user_query=user_query)
            
            # 调用LLM
            response = self.llm.invoke(prompt)
            
            # 解析JSON响应（更稳健）：支持去除代码块、提取首尾花括号、宽松容错
            try:
                content = (response.content or "").strip()

                def _strip_code_fences(text: str) -> str:
                    t = text.strip()
                    if "```json" in t:
                        s = t.find("```json") + 7
                        e = t.find("```", s)
                        if e != -1:
                            return t[s:e].strip()
                    if "```" in t:
                        s = t.find("```") + 3
                        e = t.find("```", s)
                        if e != -1:
                            return t[s:e].strip()
                    return t

                def _extract_json_object(text: str) -> str:
                    # 尝试定位首个 '{' 与最后一个 '}' 并做括号配对
                    import re
                    t = _strip_code_fences(text)
                    # 如果已经是纯 JSON 尝试直接解析
                    try:
                        json.loads(t)
                        return t
                    except Exception:
                        pass
                    # 正则粗略截取最外层对象
                    first = t.find('{')
                    last = t.rfind('}')
                    if first != -1 and last != -1 and last > first:
                        candidate = t[first:last+1]
                        # 简单括号计数校验
                        stack = 0
                        for ch in candidate:
                            if ch == '{':
                                stack += 1
                            elif ch == '}':
                                stack -= 1
                        if stack == 0:
                            return candidate.strip()
                    return t

                raw = _extract_json_object(content)
                parsed = json.loads(raw)

                # 归一化与回退：保障下游使用 rewritten_query
                normalized: Dict[str, Any] = dict(parsed)
                # 提取独立查询作为 rewritten_query 的首选
                rewritten = (
                    parsed.get("independent_query")
                    or parsed.get("rewritten_query")
                    or parsed.get("original_query")
                    or user_query
                )
                normalized["rewritten_query"] = rewritten

                # 规范 query_vectors：允许字符串列表或对象列表
                qv = parsed.get("query_vectors")
                if isinstance(qv, list):
                    fixed = []
                    for item in qv:
                        if isinstance(item, str):
                            fixed.append({"title": "变体", "query": item})
                        elif isinstance(item, dict):
                            # 统一字段名
                            q = item.get("query") or item.get("text") or ""
                            t = item.get("title") or item.get("vector_type") or "变体"
                            fixed.append({"title": t, "query": q})
                    normalized["query_vectors"] = fixed

                logger.info(f"查询架构师完成工作,重写查询: {normalized.get('rewritten_query', '解析失败')}")
                return normalized
                
            except json.JSONDecodeError as e:
                logger.exception("查询架构师返回的不是合法JSON")
                logger.debug(f"原始响应内容: {response.content}")
                
                # 返回默认结构
                return {
                    "rewritten_query": user_query,
                    "search_strategy": "默认搜索",
                    "key_concepts": [user_query],
                    "error": f"JSON解析错误: {str(e)}"
                }
                
        except Exception as e:
            logger.exception("查询架构师执行失败")
            return {
                "rewritten_query": user_query,
                "search_strategy": "默认搜索",
                "key_concepts": [user_query],
                "error": f"执行错误: {str(e)}"
            }
            
    async def abuild_context(self, user_query: str) -> Dict[str, Any]:
        """
        异步版本：构建 RAG 上下文（不生成最终答案）。

        混合检索：并发执行向量检索与BM25检索，RRF融合后重取Top-K。

        返回：{
          "rewritten_query": str,
          "context": str,
          "retrieved_chunks": list,
        }
        """
        try:
            # 步骤1：查询架构师重写查询（遵循配置，必要时启用微超时）
            if not settings.ENABLE_QUERY_REWRITING:
                rewritten_query = user_query
            else:
                try:
                    # 微超时：避免在高并发下线程池被长时间占用
                    micro_timeout = max(1.0, float(settings.CONTEXT_BUILD_TIMEOUT_SECS) - 1.0)
                    architect_result = await asyncio.wait_for(
                        asyncio.to_thread(self.run_query_architect, user_query),
                        timeout=micro_timeout,
                    )
                    rewritten_query = architect_result.get("rewritten_query", user_query)
                except Exception:
                    # 超时或错误则直接回退使用原始查询
                    rewritten_query = user_query
            standalone_query = rewritten_query

            # 意图分类：SIMPLE_RAG_MODE 下跳过，避免主路径额外 LLM 调用
            metadata_filter: Dict[str, Any] | None = None
            try:
                if (
                    not getattr(settings, "SIMPLE_RAG_MODE", True)
                    and hasattr(self, "intent_service")
                    and self.intent_service is not None
                ):
                    intent: QueryIntent = await self.intent_service.classify_intent(rewritten_query)
                    metadata_filter = intent.metadata_filter or None
                    logger.info(f"意图分类：{intent.intent}，应用过滤器：{metadata_filter}")
            except Exception as e:
                logger.warning(f"意图分类失败，继续无过滤：{e}")

            # 预先异步获取查询嵌入（双模式服务）（I2.1）
            try:
                query_embedding = await self.embedding_service.aembed_query(rewritten_query)
            except Exception:
                query_embedding = None

            # 步骤2：并发检索（向量检索 n=50 与 BM25 n=50）
            logger.info(f"(async) 混合检索：向量与BM25并发，查询: {rewritten_query}")

            def _matches_metadata_filter(md: Dict[str, Any], flt: Dict[str, Any] | None) -> bool:
                if not flt:
                    return True
                try:
                    for k, v in flt.items():
                        if isinstance(v, dict) and "$in" in v:
                            if md.get(k) not in v["$in"]:
                                return False
                        else:
                            if str(md.get(k)).strip() != str(v).strip():
                                return False
                    return True
                except Exception:
                    return False

            async def _vector_search_k50() -> Tuple[List[Tuple[Document, float]], Dict[str, float], List[str]]:
                try:
                    # 传入动态元数据过滤（如底层不支持，则由回退路径处理）
                    results = await asyncio.to_thread(
                        self.vectorstore.similarity_search_with_score,
                        rewritten_query,
                        k=50,
                        filter=metadata_filter,
                    )
                    ids: List[str] = []
                    score_map: Dict[str, float] = {}
                    for doc, score in results:
                        cid = (doc.metadata or {}).get("chunk_id")
                        if cid:
                            ids.append(cid)
                            score_map[cid] = _normalize_vector_score(score)
                    return results, score_map, ids
                except Exception:
                    # 回退：使用底层 Chroma collection 查询距离
                    try:
                        collection = self.vectorstore._collection  # type: ignore[attr-defined]
                        # 使用预先计算的查询向量（若不可用则实时计算）
                        emb = query_embedding if query_embedding is not None else await self.embedding_service.aembed_query(rewritten_query)
                        payload = await asyncio.to_thread(
                            collection.query,
                            query_embeddings=[emb],
                            n_results=50,
                            include=["distances", "documents", "metadatas", "embeddings"],
                            where=metadata_filter,
                        )
                        docs: List[Tuple[Document, float]] = []
                        score_map: Dict[str, float] = {}
                        ids: List[str] = []
                        for i in range(len(payload.get("ids", [[]])[0])):
                            cid = payload["ids"][0][i]
                            text = payload["documents"][0][i]
                            md = payload["metadatas"][0][i]
                            dist = payload["distances"][0][i]
                            # 以(1 - 距离)作为相似度近似
                            score = _normalize_vector_score(1.0 - float(dist))
                            d = Document(page_content=text, metadata=md)
                            docs.append((d, score))
                            ids.append(cid)
                            score_map[cid] = score
                        return docs, score_map, ids
                    except Exception:
                        return [], {}, []

            async def _bm25_search_k50() -> Tuple[List[str], Dict[str, float]]:
                if not self.bm25_available or not self.bm25_index:
                    return [], {}
                try:
                    tokens = [t.strip() for t in jieba.lcut(" ".join(rewritten_query.split())) if t.strip()]
                except Exception:
                    tokens = [t.strip() for t in rewritten_query.split() if t.strip()]
                try:
                    model = self.bm25_index.get("bm25")
                    ids = self.bm25_index.get("ids") or []
                    scores_all = model.get_scores(tokens) if hasattr(model, "get_scores") else []
                    scored = [(ids[i], float(scores_all[i])) for i in range(len(ids))]
                    scored.sort(key=lambda x: x[1], reverse=True)
                    top_scored = scored[:50]
                    bm25_ids = [cid for cid, _ in top_scored]
                    bm25_scores = {cid: s for cid, s in top_scored}

                    # 应用动态元数据过滤（通过底层元数据获取）
                    if metadata_filter:
                        try:
                            collection = self.vectorstore._collection  # type: ignore[attr-defined]
                            payload = await asyncio.to_thread(collection.get, ids=bm25_ids, include=["metadatas", "ids"])
                            ids_list = payload.get("ids", []) or []
                            metas_list = payload.get("metadatas", []) or []
                            filtered_ids: List[str] = []
                            filtered_scores: Dict[str, float] = {}
                            for i in range(len(ids_list)):
                                cid = ids_list[i]
                                md = metas_list[i] or {}
                                if _matches_metadata_filter(md, metadata_filter):
                                    filtered_ids.append(cid)
                                    filtered_scores[cid] = bm25_scores.get(cid, 0.0)
                            bm25_ids = filtered_ids
                            bm25_scores = filtered_scores
                        except Exception as e:
                            logger.warning(f"BM25 过滤应用失败，继续未过滤结果：{e}")

                    return bm25_ids, bm25_scores
                except Exception:
                    return [], {}

            (vector_docs_scores, vector_score_map, vector_ids), (bm25_ids, bm25_score_map) = await asyncio.gather(
                _vector_search_k50(),
                _bm25_search_k50(),
            )

            if not vector_ids and not bm25_ids:
                logger.warning("(async) 未检索到任何结果")
                self.last_run = {"rewritten_query": rewritten_query, "retrieved_chunks": []}
                return {"rewritten_query": rewritten_query, "context": "", "retrieved_chunks": []}

            # 步骤3：RRF融合（k=60），支持纯向量回退
            lists_to_fuse: List[List[str]] = []
            if vector_ids:
                lists_to_fuse.append(vector_ids)
            if bm25_ids:
                lists_to_fuse.append(bm25_ids)
            fused_ids, rrf_scores = reciprocal_rank_fusion(lists_to_fuse, k=60, top_n=None)

            # 步骤4：重取 Top-K 文档块
            top_k = settings.MAX_RETRIEVED_CHUNKS
            top_ids = fused_ids[: top_k]
            top_docs = await asyncio.to_thread(self._refetch_chunks_by_ids, top_ids)

            # 构建上下文字符串（纯CPU操作，直接在协程内执行）
            context_parts: List[str] = []
            for i, doc in enumerate(top_docs, 1):
                metadata_info = []
                if doc.metadata.get('document_title'):
                    metadata_info.append(f"文档标题: {doc.metadata['document_title']}")
                if doc.metadata.get('product_name'):
                    metadata_info.append(f"产品名称: {doc.metadata['product_name']}")
                if doc.metadata.get('effective_date'):
                    metadata_info.append(f"生效日期: {doc.metadata['effective_date']}")
                if doc.metadata.get('document_type'):
                    metadata_info.append(f"文档类型: {doc.metadata['document_type']}")
                metadata_str = " | ".join(metadata_info) if metadata_info else "无元数据"
                context_parts.append(f"【相关文档{i}】\n{metadata_str}\n内容: {doc.page_content}\n")
            final_context = "\n".join(context_parts)

            # 审计输出：结构化片段（添加 vector_score / bm25_score / rrf_score）
            retrieved_chunks: List[Dict[str, Any]] = []
            try:
                for doc in top_docs:
                    md = doc.metadata or {}
                    cid = md.get("chunk_id")
                    md["vector_score"] = vector_score_map.get(cid)
                    md["bm25_score"] = bm25_score_map.get(cid)
                    md["rrf_score"] = rrf_scores.get(cid)
                    rd = md.get("ranking_details", {})
                    # prefer vector cosine over rrf for UI + refusal gate
                    sim = (
                        rd.get("original_similarity")
                        or md.get("vector_score")
                        or md.get("rrf_score")
                        or md.get("bm25_score")
                        or 0.0
                    )
                    try:
                        sim = float(sim)
                    except Exception:
                        sim = 0.0
                    retrieved_chunks.append({
                        "chunk_id": md.get("chunk_id"),
                        "document_id": md.get("document_id"),
                        "document_name": md.get("document_title") or md.get("filename") or md.get("source"),
                        "content": doc.page_content,
                        "page_number": md.get("page_number"),
                        "similarity_score": sim,
                        "metadata": {
                            "ranking_details": rd,
                            "document_type": md.get("document_type"),
                            "product_name": md.get("product_name"),
                            "effective_date": md.get("effective_date"),
                            "expiry_date": md.get("expiry_date"),
                            "abolition_date": md.get("abolition_date"),
                            "keywords_json": md.get("keywords_json"),
                            "vector_score": md.get("vector_score"),
                            "bm25_score": md.get("bm25_score"),
                            "rrf_score": md.get("rrf_score"),
                        },
                    })
                self.last_run = {
                    "rewritten_query": rewritten_query,
                    "retrieved_chunks": retrieved_chunks,
                }
            except Exception:
                self.last_run = {
                    "rewritten_query": rewritten_query,
                    "retrieved_chunks": [],
                }

            return {
                "rewritten_query": rewritten_query,
                "context": final_context,
                "retrieved_chunks": retrieved_chunks,
            }
        except Exception:
            logger.exception("(async) 构建上下文失败")
            self.last_run = {"rewritten_query": user_query, "retrieved_chunks": []}
            return {"rewritten_query": user_query, "context": "", "retrieved_chunks": []}

    def set_bm25_resources(self, index_payload: Any, chunk_map: Dict[str, str]) -> None:
        try:
            self.bm25_index = index_payload
            self.bm25_chunk_map = chunk_map or {}
            self.bm25_available = bool(index_payload)
            logger.info("BM25 资源已注入到 RAGWorkflow")
        except Exception as e:
            logger.warning(f"BM25 资源注入失败: {e}")

    def _refetch_chunks_by_ids(self, chunk_ids: List[str]) -> List[Document]:
        try:
            collection = self.vectorstore._collection  # type: ignore[attr-defined]
            # (FIX-1.2) 获取预存嵌入向量，避免在排序阶段重复计算
            payload = collection.get(ids=chunk_ids, include=["documents", "metadatas", "embeddings"])
            out: List[Document] = []
            for i in range(len(payload.get("ids", []))):
                text = payload.get("documents", [None])[i]
                md = payload.get("metadatas", [None])[i] or {}
                try:
                    emb = payload.get("embeddings", [None])[i]
                except Exception:
                    emb = None
                # (FIX-1.3) 可选：将嵌入向量附加到元数据，供排序使用
                if emb is not None:
                    try:
                        md["embedding"] = emb
                    except Exception:
                        pass
                out.append(Document(page_content=text, metadata=md))
            return out
        except Exception:
            return []
    


# 创建全局智能代理实例
def get_agent() -> InsurIntellectAgent:
    """
    获取InsurIntellect智能代理实例
    
    Returns:
        InsurIntellectAgent: 智能代理实例
    """
    if not hasattr(get_agent, '_instance') or get_agent._instance is None:
        try:
            get_agent._instance = InsurIntellectAgent()
        except Exception as e:
            logger.exception("InsurIntellectAgent初始化失败")
            # 不缓存失败的实例,下次调用时重新尝试
            get_agent._instance = None
            raise
    return get_agent._instance


def reset_agent():
    """重置智能代理实例, 强制重新初始化"""
    if hasattr(get_agent, '_instance'):
        get_agent._instance = None


def set_bm25_resources(index_payload: Any, chunk_map: Dict[str, str]) -> None:
    agent = get_agent()
    agent.set_bm25_resources(index_payload, chunk_map)


if __name__ == "__main__":
    # 手工冒烟入口：直接检索 + RRF 融合（不跑 long-running agent 链）
    import asyncio

    agent = InsurIntellectAgent()
    test_query = "什么是车险的免赔额？"
    try:
        result = asyncio.run(agent.abuild_context(test_query, top_k=5))
    except Exception as exc:  # pragma: no cover - 仅本地手动跑
        logger.error("abuild_context failed: %s", exc, exc_info=True)
        raise
    logger.info("用户问题: %s", test_query)
    logger.info("检索结果 chunks: %d", len(result.get("chunks", [])) if isinstance(result, dict) else 0)


