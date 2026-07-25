"""
嵌入服务（双模式）
提供统一的查询/文档嵌入接口，支持：
- 本地 HuggingFaceEmbeddings（通过前缀 hf:/local: 指定）
- 远程 OpenAIEmbeddings（兼容硅基流动网关）

并提供异步方法 aembed_query/aembed_documents（对同步接口进行线程包装）。
"""

from __future__ import annotations
from typing import List, Sequence, Optional
import asyncio

from app.core.config import settings
from app.core.app_logging import get_logger

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
import torch


logger = get_logger(__name__)


class EmbeddingService:
    """统一嵌入服务（双模式）。"""

    def __init__(self, model_name: Optional[str] = None) -> None:
        # 读取模型名称（I1.2）
        self.model_name = (model_name or settings.OPENAI_EMBEDDING_MODEL or "").strip()

        # 分支加载（I1.3）
        lower = self.model_name.lower()
        if lower.startswith("local:hash") or lower in {"local-hash", "hash", "offline"}:
            from app.services.local_hash_embeddings import LocalHashEmbeddings
            logger.info("初始化离线 LocalHashEmbeddings（演示默认，无需下载模型）")
            self._embedding = LocalHashEmbeddings(dim=384)
            self.provider = "local_hash"
        elif lower.startswith("hf:") or lower.startswith("local:"):
            # 本地/HF 模型；下载失败时回退 hash，保证主演示可跑
            local_model = self.model_name.split(":", 1)[1] if ":" in self.model_name else self.model_name
            try:
                if HuggingFaceEmbeddings is None:
                    raise RuntimeError("HuggingFaceEmbeddings 未安装或不可用")
                logger.info(f"初始化本地 HuggingFaceEmbeddings: model={local_model}")
                _device = "cuda" if torch.cuda.is_available() else "cpu"
                self._embedding = HuggingFaceEmbeddings(
                    model_name=local_model,
                    model_kwargs={"device": _device},
                    encode_kwargs={"batch_size": 32},
                )
                self.provider = "huggingface"
            except Exception as e:
                from app.services.local_hash_embeddings import LocalHashEmbeddings
                logger.warning(f"HuggingFace 嵌入不可用，回退 LocalHashEmbeddings: {e}")
                self._embedding = LocalHashEmbeddings(dim=384)
                self.provider = "local_hash"
        else:
            if OpenAIEmbeddings is None:
                raise RuntimeError("OpenAIEmbeddings 未安装或不可用")
            # 兼容硅基流动代理（与 ingest.py 保持一致）
            api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
            base_url = settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL
            remote_model = self.model_name or "BAAI/bge-large-zh-v1.5"
            logger.info(f"初始化远程 OpenAIEmbeddings: base_url={base_url}, model={remote_model}")
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

    async def aembed_query(self, text: str) -> List[float]:
        """异步获取单条查询的向量嵌入（I1.4）。"""
        embedder = self._embedding
        # 优先使用原生异步方法（若存在）；否则使用线程包装同步方法
        if hasattr(embedder, "aembed_query"):
            return await embedder.aembed_query(text)  # type: ignore[attr-defined]
        return await asyncio.to_thread(embedder.embed_query, text)

    async def aembed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        """异步批量获取文档的向量嵌入。"""
        embedder = self._embedding
        if hasattr(embedder, "aembed_documents"):
            return await embedder.aembed_documents(list(texts))  # type: ignore[attr-defined]
        return await asyncio.to_thread(embedder.embed_documents, list(texts))

