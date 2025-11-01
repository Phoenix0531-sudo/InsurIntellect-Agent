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
from typing import Dict, List, Any
from datetime import datetime

# 在导入langchain之前设置环境变量
from app.core.config import settings
os.environ["OPENAI_API_KEY"] = settings.SILICONFLOW_API_KEY  # 使用硅基流动的API密钥
os.environ["OPENAI_BASE_URL"] = settings.SILICONFLOW_BASE_URL  # 使用硅基流动的基础URL

from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_chroma import Chroma

# 导入应用配置和提示模板
from app.prompts import (
    QUERY_ARCHITECT_PROMPT,
    LEAD_REVIEWER_PROMPT,
    REPORT_AUTHOR_PROMPT
)

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
            
            # 初始化嵌入模型
            self.embeddings = OpenAIEmbeddings(
                model=settings.OPENAI_EMBEDDING_MODEL,
                api_key=settings.SILICONFLOW_API_KEY,  # 显式传递API密钥
                base_url=settings.SILICONFLOW_BASE_URL  # 显式传递基础URL
            )
            logger.info("嵌入模型初始化成功")
            
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
            
            # 解析JSON响应
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
                logger.info(f"查询架构师完成工作,重写查询: {result.get('rewritten_query', '解析失败')}")
                return result
                
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
            
            # 步骤4：整理最终上下文并按时效性重排序
            logger.info("整理上下文信息并按时效性排序...")
            
            # 按文档的有效日期进行排序（如果有的话）
            def get_date_score(doc):
                """根据文档日期计算时效性分数,越新的文档分数越高"""
                try:
                    effective_date = doc.metadata.get('effective_date', '')
                    if effective_date and effective_date != '未知':
                        # 尝试解析日期
                        date_obj = datetime.strptime(effective_date, '%Y-%m-%d')
                        # 计算距离现在的天数,越近分数越高
                        days_diff = (datetime.now() - date_obj).days
                        return max(0, 10000 - days_diff)  # 基础分数减去天数差
                except:
                    pass
                return 0  # 无法解析日期的文档分数为0
            
            # 按时效性重排序
            selected_docs.sort(key=get_date_score, reverse=True)
            
            # 构建上下文字符串
            context_parts = []
            for i, doc in enumerate(selected_docs, 1):
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


if __name__ == "__main__":
    # 测试代码
    agent = InsurIntellectAgent()
    test_query = "什么是车险的免赔额？"
    result = agent.answer(test_query)
    logger.info(f"用户问题: {test_query}")
    logger.info(f"智能代理回答: {result}")


