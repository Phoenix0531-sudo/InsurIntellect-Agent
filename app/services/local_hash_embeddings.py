"""Offline local embeddings for demo (no HuggingFace / no remote API)."""

from __future__ import annotations

import hashlib
import re
from typing import List

import numpy as np


def _tokens(text: str) -> List[str]:
    text = (text or "").lower()
    # Chinese chars as unigrams + latin words
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    en = re.findall(r"[a-z0-9]+", text)
    # also bigrams for Chinese to improve recall a bit
    bigrams = [zh[i] + zh[i + 1] for i in range(len(zh) - 1)] if len(zh) > 1 else []
    return zh + bigrams + en


class LocalHashEmbeddings:
    """Deterministic bag-of-tokens hashing embedder (LangChain-compatible surface)."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> List[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        toks = _tokens(text)
        if not toks:
            return vec.tolist()
        for tok in toks:
            h = hashlib.md5(tok.encode("utf-8")).hexdigest()
            idx = int(h[:8], 16) % self.dim
            sign = 1.0 if (int(h[8:10], 16) % 2 == 0) else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_query(self, text: str) -> List[float]:
        return self._embed_one(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    # async aliases used by some callers
    async def aembed_query(self, text: str) -> List[float]:
        return self.embed_query(text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embed_documents(texts)
