"""
向量存储服务
负责向量数据库的管理和相似度搜索
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import numpy as np
from openai import AsyncOpenAI
import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session
try:
    import pinecone
except ImportError:
    pinecone = None
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk
from app.models.database_models import DocumentChunk

logger = get_logger(__name__)


class VectorStoreService:
    """向量存储服务类"""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.embedding_model = settings.EMBEDDING_MODEL
        
        # 初始化OpenAI客户端
        self.openai_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
    
    async def initialize(self):
        """初始化向量数据库"""
        try:
            if settings.VECTOR_DB_TYPE.lower() in ["chroma", "chromadb"]:
                await self._initialize_chromadb()
            elif settings.VECTOR_DB_TYPE.lower() == "pinecone":
                await self._initialize_pinecone()
            else:
                raise ValueError(f"不支持的向量数据库类型: {settings.VECTOR_DB_TYPE}")
            
            logger.info(f"向量数据库初始化完成: {settings.VECTOR_DB_TYPE}")
            
        except Exception as e:
            logger.error(f"向量数据库初始化失败: {e}")
            raise
    
    async def _initialize_chromadb(self):
        """初始化ChromaDB"""
        try:
            from app.core.chromadb_manager import chroma_manager
            
            # 使用单例管理器获取客户端和集合
            self.client = chroma_manager.get_client()
            self.collection = chroma_manager.get_collection("insurance_documents")
            
            logger.info(f"ChromaDB初始化完成，使用单例管理器")
            logger.info(f"现有ChromaDB集合: insurance_documents")
            
        except Exception as e:
            logger.error(f"ChromaDB初始化失败: {e}")
            raise
    
    async def _initialize_pinecone(self):
        """初始化Pinecone"""
        try:
            if pinecone is None:
                raise ImportError("Pinecone package not installed. Install with: pip install pinecone-client")
            
            # 初始化Pinecone
            pinecone.init(
                api_key=settings.PINECONE_API_KEY,
                environment=settings.PINECONE_ENVIRONMENT
            )
            
            # 检查索引是否存在
            if settings.PINECONE_INDEX_NAME not in pinecone.list_indexes():
                # 创建索引
                pinecone.create_index(
                    name=settings.PINECONE_INDEX_NAME,
                    dimension=1536,  # OpenAI embedding维度
                    metric="cosine"
                )
                logger.info(f"创建新的Pinecone索引: {settings.PINECONE_INDEX_NAME}")
            
            self.index = pinecone.Index(settings.PINECONE_INDEX_NAME)
            logger.info(f"连接到Pinecone索引: {settings.PINECONE_INDEX_NAME}")
            
        except Exception as e:
            logger.error(f"Pinecone初始化失败: {e}")
            raise
    
    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        try:
            response = await self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            raise
    
    async def add_document_chunks(self, db: Session, document_id: int) -> bool:
        """将文档块添加到向量数据库"""
        try:
            # 获取文档块
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).all()
            
            if not chunks:
                logger.warning(f"文档 {document_id} 没有找到块")
                return False
            
            # 批量处理块
            texts = [chunk.content for chunk in chunks]
            chunk_ids = [f"chunk_{chunk.id}" for chunk in chunks]
            
            # 获取嵌入向量
            embeddings = []
            for text in texts:
                embedding = await self.get_embedding(text)
                embeddings.append(embedding)
            
            # 准备元数据
            metadatas = []
            for chunk in chunks:
                metadata = {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number or 0,
                    "content_hash": chunk.content_hash
                }
                metadatas.append(metadata)
            
            # 添加到向量数据库
            if settings.VECTOR_DB_TYPE.lower() in ["chroma", "chromadb"]:
                await self._add_to_chromadb(chunk_ids, embeddings, metadatas, texts)
            elif settings.VECTOR_DB_TYPE.lower() == "pinecone":
                await self._add_to_pinecone(chunk_ids, embeddings, metadatas)
            
            # 更新数据库中的vector_id
            for i, chunk in enumerate(chunks):
                chunk.vector_id = chunk_ids[i]
            db.commit()
            
            logger.info(f"成功添加 {len(chunks)} 个文档块到向量数据库")
            return True
            
        except Exception as e:
            logger.error(f"添加文档块到向量数据库失败: {e}")
            return False
    
    async def _add_to_chromadb(self, ids: List[str], embeddings: List[List[float]], 
                              metadatas: List[Dict], documents: List[str]):
        """添加到ChromaDB"""
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
    
    async def _add_to_pinecone(self, ids: List[str], embeddings: List[List[float]], 
                              metadatas: List[Dict]):
        """添加到Pinecone"""
        vectors = [(ids[i], embeddings[i], metadatas[i]) for i in range(len(ids))]
        self.index.upsert(vectors=vectors)
    
    async def similarity_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """相似度搜索"""
        try:
            # 获取查询的嵌入向量
            query_embedding = await self.get_embedding(query)
            
            # 执行搜索
            if settings.VECTOR_DB_TYPE.lower() in ["chroma", "chromadb"]:
                results = await self._search_chromadb(query_embedding, top_k)
            elif settings.VECTOR_DB_TYPE.lower() == "pinecone":
                results = await self._search_pinecone(query_embedding, top_k)
            else:
                raise ValueError(f"不支持的向量数据库类型: {settings.VECTOR_DB_TYPE}")
            
            logger.info(f"相似度搜索完成，返回 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            return []
    
    async def _search_chromadb(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """在ChromaDB中搜索"""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        search_results = []
        for i in range(len(results['ids'][0])):
            result = {
                'id': results['ids'][0][i],
                'content': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'similarity_score': 1 - results['distances'][0][i]  # 转换距离为相似度
            }
            search_results.append(result)
        
        return search_results
    
    async def _search_pinecone(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """在Pinecone中搜索"""
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True
        )
        
        search_results = []
        for match in results['matches']:
            result = {
                'id': match['id'],
                'metadata': match['metadata'],
                'similarity_score': match['score']
            }
            search_results.append(result)
        
        return search_results
    
    async def delete_document_vectors(self, db: Session, document_id: int) -> bool:
        """删除文档的向量数据"""
        try:
            # 获取文档块的vector_id
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).all()
            
            if not chunks:
                return True
            
            vector_ids = [chunk.vector_id for chunk in chunks if chunk.vector_id]
            
            if not vector_ids:
                return True
            
            # 从向量数据库删除
            if settings.VECTOR_DB_TYPE.lower() in ["chroma", "chromadb"]:
                self.collection.delete(ids=vector_ids)
            elif settings.VECTOR_DB_TYPE.lower() == "pinecone":
                self.index.delete(ids=vector_ids)
            
            logger.info(f"成功删除 {len(vector_ids)} 个向量")
            return True
            
        except Exception as e:
            logger.error(f"删除向量数据失败: {e}")
            return False
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            if settings.VECTOR_DB_TYPE.lower() == "chromadb":
                if self.collection is None:
                    logger.warning("ChromaDB collection is None")
                    return {"total_vectors": 0, "type": "chromadb", "error": "collection_not_initialized"}
                count = self.collection.count()
                return {"total_vectors": count, "type": "chromadb"}
            elif settings.VECTOR_DB_TYPE.lower() == "pinecone":
                if self.index is None:
                    logger.warning("Pinecone index is None")
                    return {"total_vectors": 0, "type": "pinecone", "error": "index_not_initialized"}
                stats = self.index.describe_index_stats()
                return {"total_vectors": stats['total_vector_count'], "type": "pinecone"}
            else:
                return {"total_vectors": 0, "type": settings.VECTOR_DB_TYPE, "error": "unsupported_type"}
            
        except Exception as e:
            logger.error(f"获取集合统计信息失败: {e}")
            return {"total_vectors": 0, "type": settings.VECTOR_DB_TYPE, "error": str(e)}
    
    async def close(self):
        """关闭连接"""
        try:
            if self.client:
                # ChromaDB会自动处理连接关闭
                pass
            logger.info("向量数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭向量数据库连接失败: {e}")