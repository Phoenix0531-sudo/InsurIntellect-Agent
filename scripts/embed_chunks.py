import os
import json
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

from dotenv import load_dotenv
from app.core.config import settings
from app.core.chromadb_manager import chroma_manager
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# 简单的本地嵌入实现，避免网络依赖
class SimpleLocalEmbeddings:
    """简单的本地嵌入实现，使用TF-IDF向量化"""
    
    def __init__(self, model_name="simple-local"):
        self.model_name = model_name
        self.vocab = {}
        self.idf = {}
        self.dimension = 384  # 固定维度
        
    def _tokenize(self, text: str) -> List[str]:
        """简单的分词"""
        import re
        # 简单的中英文分词
        tokens = re.findall(r'[\w\u4e00-\u9fff]+', text.lower())
        return tokens
    
    def _build_vocab(self, texts: List[str]):
        """构建词汇表"""
        word_counts = {}
        doc_counts = {}
        
        for text in texts:
            tokens = self._tokenize(text)
            unique_tokens = set(tokens)
            
            for token in tokens:
                word_counts[token] = word_counts.get(token, 0) + 1
            
            for token in unique_tokens:
                doc_counts[token] = doc_counts.get(token, 0) + 1
        
        # 选择最常见的词作为词汇表
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        self.vocab = {word: idx for idx, (word, _) in enumerate(sorted_words[:self.dimension])}
        
        # 计算IDF
        total_docs = len(texts)
        for word in self.vocab:
            self.idf[word] = np.log(total_docs / (doc_counts.get(word, 1) + 1))
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        if not self.vocab:
            self._build_vocab(texts)
        
        embeddings = []
        for text in texts:
            tokens = self._tokenize(text)
            vector = np.zeros(self.dimension)
            
            # TF-IDF向量化
            token_counts = {}
            for token in tokens:
                token_counts[token] = token_counts.get(token, 0) + 1
            
            for token, count in token_counts.items():
                if token in self.vocab:
                    idx = self.vocab[token]
                    tf = count / len(tokens) if tokens else 0
                    idf = self.idf.get(token, 0)
                    vector[idx] = tf * idf
            
            # 归一化
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm
            
            embeddings.append(vector.tolist())
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        return self.embed_documents([text])[0]


def _load_embeddings():
    """Return an embedding function, defaulting to remote (SiliconFlow via OpenAI API-compatible).
    Set USE_LOCAL_EMBEDDINGS=1 to use simple local embeddings.
    """
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "0") == "1"

    if use_local:
        print("使用简单本地嵌入模型（TF-IDF）...")
        return SimpleLocalEmbeddings()

    # Remote provider via SiliconFlow-compatible base_url
    return OpenAIEmbeddings(
        api_key=settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY,
        base_url=settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL,
        model=settings.OPENAI_EMBEDDING_MODEL,
    )


def _init_vectorstore(embeddings, collection_name: str):
    client = chroma_manager.get_client()
    return Chroma(
        client=client,
        collection_name=collection_name,
        persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
        embedding_function=embeddings,
    )


def embed_chunks_from_file(chunks_file: Path, collection_name: str):
    load_dotenv(override=True)
    if not chunks_file.exists():
        raise FileNotFoundError(f"未找到分割产物文件: {chunks_file}")

    # 首先计算总行数用于进度显示
    total_lines = 0
    with chunks_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total_lines += 1
    
    print(f"开始处理 {total_lines} 个文档块...")

    # 可选清库重建
    if os.getenv("REBUILD_VECTOR_DB", "0") == "1":
        print("清理现有向量数据库...")
        pd = Path(settings.CHROMA_PERSIST_DIRECTORY)
        if pd.exists():
            for p in pd.glob("**/*"):
                try:
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass
            try:
                pd.rmdir()
            except Exception:
                pass

    embeddings = _load_embeddings()
    vs = _init_vectorstore(embeddings, collection_name)

    batch_size = int(os.getenv("DOC_BATCH_SIZE", "32"))
    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    ids: List[str] = []
    
    processed_count = 0
    batch_count = 0

    def _flush():
        nonlocal batch_count
        if not texts:
            return
        
        batch_count += 1
        print(f"处理批次 {batch_count}，包含 {len(texts)} 个文档块...")
        
        # 简单重试策略以应对远端速率限制或瞬时网络问题
        max_retries = 3
        delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                vs.add_texts(texts=texts, metadatas=metas, ids=ids)
                print(f"✓ 批次 {batch_count} 成功写入向量数据库")
                break
            except Exception as e:
                msg = str(e)
                print(f"⚠ 批次 {batch_count} 写入失败 (尝试 {attempt}/{max_retries}): {msg}")
                
                # 遇到网络连接错误时，尝试切换到本地嵌入模型
                if "Connection error" in msg or "TLS/SSL" in msg or "EOF" in msg or "proxy" in msg or "network" in msg:
                    try:
                        print("检测到网络连接问题，尝试切换到本地嵌入模型...")
                        fallback = SimpleLocalEmbeddings()
                        vs._embedding_function = fallback
                        vs.add_texts(texts=texts, metadatas=metas, ids=ids)
                        print(f"✓ 批次 {batch_count} 使用本地模型成功写入")
                        break
                    except Exception as fallback_e:
                        print(f"本地模型也失败: {fallback_e}")
                
                # 遇到模型上下文限制时，尝试切换到更通用的 bge-m3
                elif ("512" in msg and "token" in msg) or ("maximum context" in msg and "512" in msg) or "context_length_exceeded" in msg:
                    try:
                        print("尝试切换到 bge-m3 模型...")
                        fallback = OpenAIEmbeddings(
                            api_key=settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY,
                            base_url=settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL,
                            model="BAAI/bge-m3",
                        )
                        vs._embedding_function = fallback
                        vs.add_texts(texts=texts, metadatas=metas, ids=ids)
                        print(f"✓ 批次 {batch_count} 使用 bge-m3 成功写入")
                        break
                    except Exception as fallback_e:
                        print(f"bge-m3 回退也失败: {fallback_e}")
                        # 若回退仍失败则继续重试流程
                        pass
                if attempt >= max_retries:
                    raise
                print(f"等待 {delay:.1f} 秒后重试...")
                time.sleep(delay)
                delay *= 2

        # 清空缓冲区
        texts.clear()
        metas.clear()
        ids.clear()

    # 流式读取 JSONL 并分批写入，使用进度条
    with chunks_file.open("r", encoding="utf-8") as f:
        with tqdm(total=total_lines, desc="嵌入文档块", unit="块") as pbar:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                texts.append(item.get("text", ""))
                metas.append(item.get("metadata", {}))
                ids.append(item.get("id", ""))
                processed_count += 1
                pbar.update(1)
                
                if len(texts) >= batch_size:
                    _flush()

    _flush()
    
    print(f"✓ 完成！共处理 {processed_count} 个文档块，分 {batch_count} 个批次写入向量数据库")
    print("向量数据库已自动持久化")


if __name__ == "__main__":
    file_path = os.getenv("CHUNKS_FILE", "data/processed/chunks.jsonl")
    collection = os.getenv("COLLECTION_NAME", "insurance_documents")
    embed_chunks_from_file(Path(file_path), collection)
    print(f"已完成嵌入并写库：{file_path} -> 集合 {collection}")

