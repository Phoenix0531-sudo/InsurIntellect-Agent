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
from typing import Dict, List, Any, Tuple
from datetime import datetime
import asyncio

# 在导入langchain之前设置环境变量
from app.core.config import settings
os.environ["OPENAI_API_KEY"] = settings.SILICONFLOW_API_KEY  # 使用硅基流动的API密钥
os.environ["OPENAI_BASE_URL"] = settings.SILICONFLOW_BASE_URL  # 使用硅基流动的基础URL

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_chroma import Chroma
# 新增导入：用于构建提示与解析输出（AI判别辅助）
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
            # 初始化ChatOpenAI LLM（兼容硅基流动）
            self.llm = ChatOpenAI(
                model=settings.SILICONFLOW_MODEL,  # 使用硅基流动的模型
                temperature=settings.OPENAI_TEMPERATURE,
                max_tokens=settings.OPENAI_MAX_TOKENS,
                api_key=settings.SILICONFLOW_API_KEY,  # 显式传递API密钥
                base_url=settings.SILICONFLOW_BASE_URL  # 显式传递基础URL
            )
            logger.info("ChatOpenAI LLM初始化成功")
            
            # 初始化嵌入服务（双模式）
            self.embedding_service = EmbeddingService(model_name=settings.OPENAI_EMBEDDING_MODEL)
            self.embeddings = self.embedding_service.embedding_function
            logger.info("嵌入服务初始化成功（双模式）")
            # 额外记录到应用主日志记录器，确保写入 logs/app.log
            try:
                app_get_logger("insurintellect").info("嵌入服务初始化成功（双模式）")
            except Exception:
                pass
            
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
            
    def run_lead_reviewer(self, user_query: str, candidates: List[Document]) -> List[Document]:
        """
        运行首席评审员:筛选最相关的文档块
        
        Args:
            user_query (str): 用户查询
            candidates (List[Document]): 候选文档块列表
            
        Returns:
            List[Document]: 筛选后的文档块列表
        """
        try:
            logger.info(f"首席评审员开始工作,评审 {len(candidates)} 个候选文档...")
            
            if not candidates:
                logger.warning("没有候选文档可供评审")
                return []
            
            # 准备候选文档信息
            candidates_info = []
            for i, doc in enumerate(candidates):
                candidates_info.append({
                    "index": i,
                    "content_preview": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                    "metadata": doc.metadata
                })
            
            # 使用LEAD_REVIEWER_PROMPT模板
            prompt = LEAD_REVIEWER_PROMPT.format(
                user_query=user_query,
                candidates=json.dumps(candidates_info, ensure_ascii=False, indent=2)
            )
            
            # 调用LLM
            response = self.llm.invoke(prompt)
            
            # 解析响应中的索引列表
            try:
                # 尝试从响应中提取JSON部分
                content = response.content.strip()
                
                # 如果响应包含代码块,提取其中的JSON
                if "```json" in content:
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    if end != -1:
                        content = content[start:end].strip()
                elif "```" in content:
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    if end != -1:
                        content = content[start:end].strip()
                
                # 尝试解析JSON
                result = json.loads(content)
                selected_indices = result.get("selected_indices", [])
                
                # 筛选文档
                selected_documents = []
                for index in selected_indices:
                    if 0 <= index < len(candidates):
                        selected_documents.append(candidates[index])
                
                logger.info(f"首席评审员完成工作,选择了{len(selected_documents)} 个相关文档")
                return selected_documents
                
            except json.JSONDecodeError as e:
                logger.exception("首席评审员返回的不是合法JSON")
                logger.debug(f"原始响应内容: {response.content}")
                # 返回前几个文档作为默认选择
                return candidates[:settings.MAX_RETRIEVED_CHUNKS]
                
        except Exception as e:
            logger.exception("首席评审员执行失败")
            # 返回前几个文档作为默认选择
            return candidates[:settings.MAX_RETRIEVED_CHUNKS]

    def _is_regulatory_query(self, user_query: str) -> bool:
        """重构：改为调用新的 AI 方法，并保留关键词回退"""
        try:
            ai_result = self._is_query_regulatory(user_query)
            if ai_result:
                return True
        except Exception:
            logger.warning("_is_query_regulatory 执行异常，启用关键词回退")
        # 当AI返回否或异常时，使用关键词回退增强鲁棒性
        query_lower = (user_query or "").lower()
        for kw in settings.REGULATORY_KEYWORDS:
            if kw.lower() in query_lower:
                logger.info("关键词命中，视为监管相关查询")
                return True
        return False

    def _is_product_document(self, doc: Document) -> bool:
        """判断是否为产品相关文档（而非监管文件）"""
        doc_type = (doc.metadata or {}).get("document_type", "")
        if not doc_type:
            return True  # 无类型信息时视为产品文档
        return "监管" not in doc_type

    def _is_associated_with_regulatory_query(self, user_query: str, doc: Document) -> bool:
        """重构：改为调用新的 AI 方法，并保留元数据回退"""
        try:
            ai_result = self._is_doc_related_to_regulatory_query(doc, user_query)
            if ai_result:
                return True
        except Exception:
            logger.warning("_is_doc_related_to_regulatory_query 执行异常，启用元数据回退")
        # 当AI返回否或异常时，使用元数据回退增强鲁棒性
        doc_type = (doc.metadata or {}).get("document_type", "")
        return "监管" not in doc_type

    def _regulatory_rerank(self, user_query: str, candidates: List[Document]) -> List[Document]:
        """
        已废弃：攻关任务四采用全新业务规则（线性加权 + 阶跃时效 + ESG 加分）。
        为保持兼容性，此方法不再更改候选顺序，直接返回原列表。
        """
        return candidates

    def run_report_author(self, user_query: str, context: str) -> str:
        """
        运行报告撰写人：生成最终答案
        
        Args:
            user_query (str): 用户查询
            context (str): 整理后的上下文信息
            
        Returns:
            str: 最终的文本答案
        """
        try:
            logger.info("报告撰写人开始工作...")
            
            # 使用REPORT_AUTHOR_PROMPT模板
            prompt = REPORT_AUTHOR_PROMPT.format(
                user_query=user_query,
                context=context
            )
            
            # 调用LLM
            response = self.llm.invoke(prompt)
            
            final_answer = response.content.strip()
            logger.info("报告撰写人完成工作,生成最终答案")
            return final_answer
            
        except Exception as e:
            logger.exception("报告撰写人执行失败")
            return f"抱歉,在生成答案时遇到了问题:{str(e)}"

    # 新增：动态排序主函数（攻关任务四规则）
    def _dynamic_ranking(self, docs: List[Document], query: str) -> List[Document]:
        """
        使用批准的业务规则进行动态排序：
        final_score = (W_orig * similarity) + (W_biz * business_score)
        business_score = timeliness_boost + compliance_boost
        规则：
        - timeliness_boost: 若 (today - effective_date) <= 180 天，则 +0.3，否则 0.0
        - compliance_boost: 文档含有 ESG 关键词（RERANK_COMPLIANCE_KEYWORDS）则 +0.1
        - expired: 若 expiry_date <= today，则 final_score *= 0.5
        - abolition: 若 abolition_date <= today，则剔除该文档块
        - 不进行 min-max 归一化；相似度为 [0,1] 的语义相似度
        - 应用 SIMILARITY_THRESHOLD 初筛
        """

        def _parse_date(d: Any) -> Any:
            if not d:
                return None
            s = str(d).strip()
            if not s or s in ("未知", "unknown"):
                return None
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    from datetime import datetime as _dt
                    return _dt.strptime(s, fmt)
                except Exception:
                    continue
            return None

        def _within_recent_180(metadata: Dict[str, Any]) -> bool:
            from datetime import datetime as _dt
            today = _dt.now()
            candidates = [metadata.get("effective_date"), metadata.get("publish_date"), metadata.get("last_updated_date")]
            latest = None
            for d in candidates:
                dt = _parse_date(d)
                if dt and (latest is None or dt > latest):
                    latest = dt
            if not latest:
                return False
            return (today - latest).days <= 180

        def _has_esg(doc: Document) -> bool:
            md = doc.metadata or {}
            # keywords_json 可以是JSON字符串或列表
            kws = md.get("keywords_json")
            keywords: List[str] = []
            try:
                if isinstance(kws, str):
                    import json as _json
                    keywords = [str(x).lower() for x in (_json.loads(kws) or [])]
                elif isinstance(kws, list):
                    keywords = [str(x).lower() for x in kws]
            except Exception:
                keywords = []
            content = (doc.page_content or "").lower()
            for kw in settings.RERANK_COMPLIANCE_KEYWORDS:
                k = kw.lower()
                if k in keywords or k in content:
                    return True
            return False

        def _expired_penalty_factor(metadata: Dict[str, Any]) -> float:
            from datetime import datetime as _dt
            today = _dt.now()
            # 常见键名兼容
            expiry_keys = ["expiry_date", "expire_date", "expiration_date", "valid_to"]
            for k in expiry_keys:
                dt = _parse_date(metadata.get(k))
                if dt and dt <= today:
                    return settings.RERANK_EXPIRED_PENALTY
            return 1.0

        def _is_abolished(metadata: Dict[str, Any]) -> bool:
            from datetime import datetime as _dt
            today = _dt.now()
            abolish_keys = ["abolition_date", "abolished_date", "repealed_date"]
            for k in abolish_keys:
                dt = _parse_date(metadata.get(k))
                if dt and dt <= today:
                    return True
            # 兼容布尔标记
            if str(metadata.get("is_abolished", "")).strip().lower() in ("true", "1", "yes"):
                return True
            return False

        def _similarity(query_text: str, doc_text: str) -> float:
            try:
                qv = self.embeddings.embed_query(query_text)
                dv = self.embeddings.embed_documents([doc_text or ""])[0]
                # 余弦相似度 -> [0,1]
                import math
                dot = sum(a * b for a, b in zip(qv, dv))
                # 防御性：避免数值溢出
                cos = max(min(dot, 1.0), -1.0)
                return (cos + 1.0) / 2.0
            except Exception:
                return 0.0

        scored: List[tuple] = []
        for doc in docs:
            md = doc.metadata or {}

            sim = _similarity(query, doc.page_content or "")
            if sim < settings.SIMILARITY_THRESHOLD:
                continue  # 初筛过滤掉语义相关度极低的

            if _is_abolished(md):
                # 废止直接剔除
                continue

            timeliness_boost = settings.RERANK_RECENCY_BOOST if _within_recent_180(md) else 0.0
            compliance_boost = settings.RERANK_COMPLIANCE_BOOST_SCORE if _has_esg(doc) else 0.0
            business_score = timeliness_boost + compliance_boost

            final_score = (settings.RERANK_ORIG_WEIGHT * sim) + (settings.RERANK_BIZ_WEIGHT * business_score)
            penalty = _expired_penalty_factor(md)
            final_score *= penalty

            # 写入审计字段
            details = {
                "original_similarity": round(sim, 6),
                "timeliness_boost": round(timeliness_boost, 6),
                "compliance_boost": round(compliance_boost, 6),
                "business_score": round(business_score, 6),
                "expired_penalty": round(penalty if penalty != 1.0 else 0.0, 6),
                "final_score": round(final_score, 6),
            }
            try:
                doc.metadata = md  # 确保可写
                doc.metadata.setdefault("ranking_details", details)
                # 若已有，则更新为当前计算结果
                doc.metadata["ranking_details"] = details
            except Exception:
                pass

            scored.append((final_score, doc))

        # 按最终分倒序
        scored.sort(key=lambda x: x[0], reverse=True)
        ranked_docs = [d for _, d in scored]
        # Top-K 截断
        return ranked_docs[: settings.MAX_RETRIEVED_CHUNKS]

    # 新增：AI辅助方法——判断查询是否与监管高度相关
    def _is_query_regulatory(self, query: str) -> bool:
        """使用AI判断一个查询是否与保险监管、法规或合规性高度相关"""
        try:
            prompt_text = (
                "请判断以下用户问题是否与保险监管、法规或合规性高度相关？"
                "请只回答'是'或'否'。\n\n"
                f"问题：'{query}'"
            )
            prompt = ChatPromptTemplate.from_template(prompt_text)
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({})
            return "是" in (response or "")
        except Exception as e:
            logger.warning(f"判断查询监管相关性时出错: {e}")
            return False

    # 新增：AI辅助方法——判断文档是否与监管相关查询高度关联
    def _is_doc_related_to_regulatory_query(self, doc: Document, query: str) -> bool:
        """使用AI判断一个文档是否与一个已知的监管相关查询高度关联"""
        try:
            doc_snippet = (doc.page_content or "")[:500]  # 取文档摘要进行判断，以提高效率
            prompt_text = (
                "已知用户问题是关于保险监管的。请判断以下文档摘要是否与这个问题高度相关？"
                "请只回答'是'或'否'。\n\n"
                f"用户问题：'{query}'\n\n文档摘要：'{doc_snippet}'"
            )
            prompt = ChatPromptTemplate.from_template(prompt_text)
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({})
            return "是" in (response or "")
        except Exception as e:
            logger.warning(f"判断文档与监管查询关联性时出错: {e}")
            return False

    def build_context(self, user_query: str) -> Dict[str, Any]:
        """
        构建 RAG 上下文（不生成最终答案）。

        执行步骤：
        1. 查询架构师重写查询
        2. 初步检索候选文档
        3. 首席评审员筛选最相关文档
        4. 动态排序与 Top-K 截断

        返回：{
          "rewritten_query": str,
          "context": str,            # 拼接后的上下文文本
          "retrieved_chunks": list,  # 结构化的片段列表（用于响应与持久化）
        }
        """
        try:
            # 步骤1：查询架构师重写查询
            architect_result = self.run_query_architect(user_query)
            rewritten_query = architect_result.get("rewritten_query", user_query)
            standalone_query = rewritten_query

            # 步骤2：初步检索
            logger.info(f"构建上下文：使用重写查询进行检索: {rewritten_query}")
            retrieved_docs = self.retriever.invoke(rewritten_query)
            if not retrieved_docs:
                logger.warning("未检索到相关文档")
                # 返回空上下文，但仍带上重写查询供外层回退
                self.last_run = {"rewritten_query": rewritten_query, "retrieved_chunks": []}
                return {"rewritten_query": rewritten_query, "context": "", "retrieved_chunks": []}

            # 步骤3：评审筛选
            selected_docs = self.run_lead_reviewer(user_query, retrieved_docs)
            if not selected_docs:
                logger.warning("首席评审员未选择任何文档")
                self.last_run = {"rewritten_query": rewritten_query, "retrieved_chunks": []}
                return {"rewritten_query": rewritten_query, "context": "", "retrieved_chunks": []}

            # 步骤4：动态排序并截断
            sorted_docs = self._dynamic_ranking(selected_docs, standalone_query)
            top_docs = sorted_docs[: settings.MAX_RETRIEVED_CHUNKS]

            # 构建上下文字符串
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

            # 审计输出：结构化片段
            retrieved_chunks: List[Dict[str, Any]] = []
            try:
                for doc in top_docs:
                    md = doc.metadata or {}
                    rd = md.get("ranking_details", {})
                    retrieved_chunks.append({
                        "chunk_id": md.get("chunk_id"),
                        "document_id": md.get("document_id"),
                        "document_name": md.get("document_title") or md.get("filename") or md.get("source"),
                        "content": doc.page_content,
                        "page_number": md.get("page_number"),
                        "similarity_score": rd.get("original_similarity"),
                        "metadata": {
                            "ranking_details": rd,
                            "document_type": md.get("document_type"),
                            "product_name": md.get("product_name"),
                            "effective_date": md.get("effective_date"),
                            "expiry_date": md.get("expiry_date"),
                            "abolition_date": md.get("abolition_date"),
                            "keywords_json": md.get("keywords_json"),
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
        except Exception as e:
            logger.exception("构建上下文失败")
            self.last_run = {"rewritten_query": user_query, "retrieved_chunks": []}
            return {"rewritten_query": user_query, "context": "", "retrieved_chunks": []}

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
            # 步骤1：查询架构师重写查询（同步 -> 线程）
            architect_result = await asyncio.to_thread(self.run_query_architect, user_query)
            rewritten_query = architect_result.get("rewritten_query", user_query)
            standalone_query = rewritten_query

            # 预先异步获取查询嵌入（双模式服务）（I2.1）
            try:
                query_embedding = await self.embedding_service.aembed_query(rewritten_query)
            except Exception:
                query_embedding = None

            # 步骤2：并发检索（向量检索 n=50 与 BM25 n=50）
            logger.info(f"(async) 混合检索：向量与BM25并发，查询: {rewritten_query}")

            async def _vector_search_k50() -> Tuple[List[Tuple[Document, float]], Dict[str, float], List[str]]:
                try:
                    results = await asyncio.to_thread(self.vectorstore.similarity_search_with_score, rewritten_query, k=50)
                    ids: List[str] = []
                    score_map: Dict[str, float] = {}
                    for doc, score in results:
                        cid = (doc.metadata or {}).get("chunk_id")
                        if cid:
                            ids.append(cid)
                            score_map[cid] = float(score)
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
                            score = 1.0 - float(dist)
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
                    retrieved_chunks.append({
                        "chunk_id": md.get("chunk_id"),
                        "document_id": md.get("document_id"),
                        "document_name": md.get("document_title") or md.get("filename") or md.get("source"),
                        "content": doc.page_content,
                        "page_number": md.get("page_number"),
                        "similarity_score": rd.get("original_similarity"),
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
            payload = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
            out: List[Document] = []
            for i in range(len(payload.get("ids", []))):
                text = payload.get("documents", [None])[i]
                md = payload.get("metadatas", [None])[i]
                out.append(Document(page_content=text, metadata=md))
            return out
        except Exception:
            return []
    
    def answer(self, user_query: str) -> str:
        """
        主方法：编排完整的 RAG 工作流
        
        执行步骤：
        1. 查询架构师重写查询
        2. 向量数据库检索相关文档
        3. 首席评审员筛选最相关文档
        4. 按时效性重排序上下文
        5. 报告撰写人生成最终答案
        
        Args:
            user_query (str): 用户查询
            
        Returns:
            str: 最终答案
        """
        logger.info(f"开始处理用户查询: {user_query}")
        
        try:
            # 步骤1：查询架构师重写查询
            architect_result = self.run_query_architect(user_query)
            rewritten_query = architect_result.get("rewritten_query", user_query)
            # 新增：独立查询（用于动态排序中的AI判断输入）
            standalone_query = rewritten_query
            
            # 步骤2：使用重写后的查询进行初步检索
            logger.info(f"使用重写查询进行检索: {rewritten_query}")
            retrieved_docs = self.retriever.invoke(rewritten_query)
            
            if not retrieved_docs:
                logger.warning("未检索到相关文档")
                return "抱歉,我没有找到与您的问题相关的信息.请尝试重新表述您的问题或提供更多详细信息."
            
            logger.info(f"初步检索到 {len(retrieved_docs)} 个文档")
            
            # 步骤3: 首席评审员筛选最相关文档
            selected_docs = self.run_lead_reviewer(user_query, retrieved_docs)
            
            if not selected_docs:
                logger.warning("首席评审员未选择任何文档")
                return "抱歉,虽然找到了一些相关信息,但经过评审后发现与您的问题关联度不够高.请尝试重新表述您的问题."
            
            # 步骤4：整理最终上下文并进行动态排序（替换原先的仅按时效性排序）
            logger.info("整理上下文信息并进行动态排序（监管规则 + AI加权）...")
            sorted_docs = self._dynamic_ranking(selected_docs, standalone_query)

            # Top-K（已在 _dynamic_ranking 中截断，这里保持一致）
            top_docs = sorted_docs[: settings.MAX_RETRIEVED_CHUNKS]

            # 构建上下文字符串
            context_parts = []
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

            # 审计输出：记录检索与排序详情，用于 QueryHistory 持久化
            try:
                retrieved_chunks = []
                for doc in top_docs:
                    md = doc.metadata or {}
                    rd = md.get("ranking_details", {})
                    retrieved_chunks.append({
                        "chunk_id": md.get("chunk_id"),
                        "document_id": md.get("document_id"),
                        "document_name": md.get("document_title") or md.get("filename") or md.get("source"),
                        "content": doc.page_content,
                        "page_number": md.get("page_number"),
                        "similarity_score": rd.get("original_similarity"),
                        "metadata": {
                            "ranking_details": rd,
                            "document_type": md.get("document_type"),
                            "product_name": md.get("product_name"),
                            "effective_date": md.get("effective_date"),
                            "expiry_date": md.get("expiry_date"),
                            "abolition_date": md.get("abolition_date"),
                            "keywords_json": md.get("keywords_json"),
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
            
            # 步骤5: 报告撰写人生成最终答案
            final_answer = self.run_report_author(user_query, final_context)
            
            logger.info("RAG工作流完成")
            return final_answer
            
        except Exception as e:
            logger.exception("RAG工作流执行失败")
            return f"抱歉,在处理您的问题时遇到了技术问题:{str(e)}.请稍后重试或联系技术支持."


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
    # 测试代码
    agent = InsurIntellectAgent()
    test_query = "什么是车险的免赔额？"
    result = agent.answer(test_query)
    logger.info(f"用户问题: {test_query}")
    logger.info(f"智能代理回答: {result}")


