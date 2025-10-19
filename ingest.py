#!/usr/bin/env python3
"""
InsurIntellect Agent - Data Ingestion Pipeline
=============================================

This script handles the data initialization phase of the project:
- Reads all PDF documents from the configured directory
- Uses AI to extract metadata from document snippets
- Chunks documents using LangChain text splitters
- Builds a local ChromaDB vector database with embeddings

Author: InsurIntellect Agent Development Team
Version: 1.0.0
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

# LangChain imports
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.chat_models import ChatSiliconFlow
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document

# Project imports
from app.core.config import settings
from prompts import DIGITAL_ARCHIVIST_PROMPT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_metadata_from_ai(text_snippet: str) -> Dict[str, Any]:
    """
    使用AI从文档文本片段中提取结构化元数据
    
    Args:
        text_snippet (str): 文档文本片段
        
    Returns:
        Dict[str, Any]: 包含元数据的字典
    """
    try:
        # 初始化硅基流动Chat模型
        chat_model = ChatSiliconFlow(
            model=settings.OPENAI_MODEL,  # 使用配置中的模型名
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            temperature=settings.OPENAI_TEMPERATURE
        )
        
        # 使用DIGITAL_ARCHIVIST_PROMPT模板
        prompt = DIGITAL_ARCHIVIST_PROMPT.format(
            document_text_snippet=text_snippet
        )
        
        logger.info("正在调用AI提取文档元数据...")
        
        # 调用AI模型
        response = chat_model.invoke(prompt)
        
        # 解析JSON响应
        try:
            metadata = json.loads(response.content)
            logger.info(f"成功提取元数据: {metadata}")
            return metadata
        except json.JSONDecodeError as e:
            logger.error(f"AI返回的不是合法的JSON: {e}")
            return {
                "document_title": "解析失败",
                "product_name": "未知",
                "effective_date": "未知",
                "document_type": "未知",
                "error": f"JSON解析错误: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"AI元数据提取失败: {e}")
        return {
            "document_title": "提取失败",
            "product_name": "未知",
            "effective_date": "未知",
            "document_type": "未知",
            "error": f"AI调用错误: {str(e)}"
        }


def main():
    """
    主函数：执行数据摄取管道的核心逻辑
    """
    logger.info("开始执行数据摄取管道...")
    
    # 定义PDF文档路径
    pdf_data_path = Path("./data/documents/pdfs")
    vector_store_path = settings.CHROMA_PERSIST_DIRECTORY
    
    # 检查PDF目录是否存在
    if not pdf_data_path.exists():
        logger.error(f"PDF数据目录不存在: {pdf_data_path}")
        return
    
    # 获取所有PDF文件
    pdf_files = list(pdf_data_path.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"在 {pdf_data_path} 目录中未找到PDF文件")
        return
    
    logger.info(f"找到 {len(pdf_files)} 个PDF文件")
    
    # 初始化文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    # 存储所有处理后的文档块
    all_documents = []
    
    # 遍历所有PDF文件
    for pdf_file in pdf_files:
        logger.info(f"正在处理文件: {pdf_file.name}")
        
        try:
            # 使用PyPDFLoader加载文档
            loader = PyPDFLoader(str(pdf_file))
            documents = loader.load()
            
            if not documents:
                logger.warning(f"文件 {pdf_file.name} 加载失败或为空")
                continue
            
            # 取第一页文本作为摘要，用于AI元数据提取
            first_page_text = documents[0].page_content[:2000]  # 限制长度避免超出token限制
            
            # 调用AI提取元数据
            ai_metadata = get_metadata_from_ai(first_page_text)
            
            # 使用文本分割器对文档进行分块
            document_chunks = text_splitter.split_documents(documents)
            
            logger.info(f"文件 {pdf_file.name} 被分割为 {len(document_chunks)} 个块")
            
            # 为每个块添加元数据
            for chunk in document_chunks:
                # 合并原有元数据和AI提取的元数据
                chunk.metadata.update({
                    "source_file": pdf_file.name,
                    "file_path": str(pdf_file),
                    **ai_metadata  # 展开AI提取的元数据
                })
            
            all_documents.extend(document_chunks)
            
        except Exception as e:
            logger.error(f"处理文件 {pdf_file.name} 时出错: {e}")
            continue
    
    if not all_documents:
        logger.error("没有成功处理任何文档")
        return
    
    logger.info(f"总共处理了 {len(all_documents)} 个文档块")
    
    # 初始化嵌入模型
    try:
        logger.info("初始化嵌入模型...")
        embeddings = OpenAIEmbeddings(
            openai_api_key=settings.OPENAI_API_KEY,
            openai_api_base=settings.OPENAI_BASE_URL,
            model=settings.OPENAI_EMBEDDING_MODEL
        )
    except Exception as e:
        logger.error(f"初始化嵌入模型失败: {e}")
        return
    
    # 创建向量数据库目录
    vector_store_dir = Path(vector_store_path)
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info("正在创建ChromaDB向量数据库...")
        
        # 使用Chroma.from_documents创建向量数据库
        vectorstore = Chroma.from_documents(
            documents=all_documents,
            embedding=embeddings,
            persist_directory=vector_store_path,
            collection_name="insurintellect_documents"
        )
        
        # 持久化数据库
        vectorstore.persist()
        
        logger.info(f"成功创建向量数据库，存储路径: {vector_store_path}")
        logger.info(f"数据库包含 {len(all_documents)} 个文档块")
        
        # 验证数据库
        collection = vectorstore._collection
        logger.info(f"向量数据库验证 - 集合大小: {collection.count()}")
        
    except Exception as e:
        logger.error(f"创建向量数据库失败: {e}")
        return
    
    logger.info("数据摄取管道执行完成！")


if __name__ == "__main__":
    main()