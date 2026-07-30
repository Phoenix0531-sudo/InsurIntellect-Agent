"""
嵌入服务（双模式）
提供统一的查询/文档嵌入接口，支持：
- 本地 HuggingFaceEmbeddings（通过前缀 hf:/local: 指定）
- 离线 LocalHashEmbeddings（local:hash）
- 远程 OpenAIEmbeddings（兼容任意 OpenAI 网关）

并提供异步方法 aembed_query/aembed_documents（对同步接口进行线程包装）。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Sequence

from app.core.app_logging import get_logger
from app.core.config import settings

try:
    from langchain_openai import OpenAIEmbeddings
except Exception:  # 运行时可选依赖
    OpenAIEmbeddings = None  # type: ignore

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except Exception:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except Exception:
        HuggingFaceEmbeddings = None  # type: ignore

logger = get_logger(__name__)


class EmbeddingService:
    """统一嵌入服务（双模式）。"""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = (model_name or settings.OPENAI_EMBEDDING_MODEL or "").strip()
        lower = self.model_name.lower()

        if lower.startswith("local:hash") or lower in {"local-hash", "hash", "offline"}:
            from app.services.local_hash_embeddings import LocalHashEmbeddings

            logger.info("初始化离线 LocalHashEmbeddings（无需下载模型）")
            self._embedding = LocalHashEmbeddings(dim=384)
            self.provider = "local_hash"
        elif lower.startswith("hf:") or lower.startswith("local:"):
            local_model = (
                self.model_name.split(":", 1)[1] if ":" in self.model_name else self.model_name
            )
            try:
                if HuggingFaceEmbeddings is None:
                    raise RuntimeError("HuggingFaceEmbeddings 未安装或不可用")
                logger.info("初始化本地 HuggingFaceEmbeddings: model=%s", local_model)
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
                # normalize_embeddings helps cosine scores stay comparable for threshold gates
                self._embedding = HuggingFaceEmbeddings(
                    model_name=local_model,
                    model_kwargs={"device": device},
                    encode_kwargs={"batch_size": 32, "normalize_embeddings": True},
                )
                # smoke one encode so fallback happens at init, not first query
                _ = self._embedding.embed_query("条款")
                self.provider = "huggingface"
            except Exception as e:
                from app.services.local_hash_embeddings import LocalHashEmbeddings

                logger.warning("HuggingFace 嵌入不可用，回退 LocalHashEmbeddings: %s", e)
                self._embedding = LocalHashEmbeddings(dim=384)
                self.provider = "local_hash"
        else:
            if OpenAIEmbeddings is None:
                raise RuntimeError("OpenAIEmbeddings 未安装或不可用")
            api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
            base_url = settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL
            remote_model = self.model_name or "BAAI/bge-large-zh-v1.5"
            logger.info(
                "初始化远程 OpenAIEmbeddings: base_url=%s, model=%s", base_url, remote_model
            )
            self._embedding = OpenAIEmbeddings(
                api_key=api_key,
                base_url=base_url,
                model=remote_model,
                timeout=60,
            )
            self.provider = "openai"

    @property
    def embedding_function(self):
        """返回底层的 Embeddings 实例，供 Chroma/LangChain 使用。"""
        return self._embedding

    def embed_query(self, text: str) -> List[float]:
        """同步查询嵌入（rag_workflow 同步路径会调用）。"""
        return self._embedding.embed_query(text)

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        """同步批量文档嵌入。"""
        return self._embedding.embed_documents(list(texts))

    async def aembed_query(self, text: str) -> List[float]:
        """异步获取单条查询的向量嵌入。"""
        embedder = self._embedding
        if hasattr(embedder, "aembed_query"):
            return await embedder.aembed_query(text)  # type: ignore[attr-defined]
        return await asyncio.to_thread(embedder.embed_query, text)

    async def aembed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        """异步批量获取文档的向量嵌入。"""
        embedder = self._embedding
        if hasattr(embedder, "aembed_documents"):
            return await embedder.aembed_documents(list(texts))  # type: ignore[attr-defined]
        return await asyncio.to_thread(embedder.embed_documents, list(texts))
