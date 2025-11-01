#!/usr/bin/env python3
"""
ChromaDB 单例管理器
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import Optional
import threading
from pathlib import Path

from app.core.config import settings
from app.core.app_logging import get_logger

logger = get_logger(__name__)


class ChromaDBManager:
    """
    提供 ChromaDB 客户端与集合的单例管理
    """

    _instance: Optional["ChromaDBManager"] = None
    _lock = threading.Lock()
    _client: Optional[chromadb.Client] = None
    _collection: Optional[chromadb.Collection] = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        logger.info("初始化 ChromaDB 管理器")

    def get_client(self) -> chromadb.Client:
        """
        获取 ChromaDB 客户端（单例）
        """
        if self._client is None:
            with self._lock:
                if self._client is None:
                    chroma_path = Path(settings.CHROMA_PERSIST_DIRECTORY)
                    chroma_path.mkdir(parents=True, exist_ok=True)

                    logger.info(f"创建 ChromaDB 持久化客户端, 路径 {chroma_path}（禁用匿名遥测）")
                    self._client = chromadb.PersistentClient(
                        path=str(chroma_path),
                        settings=ChromaSettings(
                            anonymized_telemetry=False,
                        ),
                    )
        return self._client

    def get_collection(self, collection_name: str = "insurance_documents") -> chromadb.Collection:
        """
        获取或创建 ChromaDB 集合（单例）
        """
        if self._collection is None:
            with self._lock:
                if self._collection is None:
                    client = self.get_client()
                    try:
                        self._collection = client.get_collection(name=collection_name)
                        logger.info(f"获取现有 ChromaDB 集合: {collection_name}")
                    except Exception:
                        logger.info(f"创建新 ChromaDB 集合: {collection_name}")
                        self._collection = client.create_collection(
                            name=collection_name,
                            metadata={"hnsw:space": "cosine"},
                        )

                    logger.info(f"ChromaDB 集合初始化完成, 向量数 {self._collection.count()}")
        return self._collection

    def reset_collection(self, collection_name: str = "insurance_documents") -> None:
        """
        重置集合（删除并重新创建）
        """
        with self._lock:
            client = self.get_client()
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"删除 ChromaDB 集合: {collection_name}")
            except Exception as e:
                logger.warning(f"删除集合失败（可能不存在）: {e}")

            self._collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"重新创建 ChromaDB 集合: {collection_name}")

    def close(self) -> None:
        """
        关闭 ChromaDB 连接
        """
        with self._lock:
            if self._client is not None:
                logger.info("关闭 ChromaDB 连接")
                self._client = None
                self._collection = None

    @classmethod
    def get_instance(cls) -> "ChromaDBManager":
        """获取单例实例"""
        return cls()


# 全局单例实例
chroma_manager = ChromaDBManager()

