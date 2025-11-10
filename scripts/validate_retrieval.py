import json
import argparse
from pathlib import Path

from app.core.config import settings
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from app.core.chromadb_manager import chroma_manager
from app.core.app_logging import setup_logging, get_logger

logger = get_logger(__name__)


def run_verification(question: str, top_k: int = 5) -> Path:
    # 初始化嵌入与 Chroma 持久化
    embeddings = OpenAIEmbeddings(
        api_key=(settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY),
        base_url=(settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL),
        model=settings.OPENAI_EMBEDDING_MODEL,
        timeout=60,
    )

    # 使用与应用一致的持久客户端与集合名称
    chroma_client = chroma_manager.get_client()
    vectorstore = Chroma(
        client=chroma_client,
        collection_name="insurance_documents",
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
    )

    # 集合条数
    collection_count = 0
    try:
        collection_count = vectorstore._collection.count()
    except Exception:
        pass

    # 统计 OCR 页数（基于元数据中的 extraction_method == 'ocr' 的唯一页）
    ocr_pages_count = 0
    try:
        res = vectorstore._collection.get(
            where={"extraction_method": "ocr"},
            include=["metadatas"],
            limit=500000,
        )
        metas = res.get("metadatas") or []
        seen_pages = set()
        for m in metas:
            if not isinstance(m, dict):
                continue
            method = m.get("extraction_method")
            src = m.get("source_file")
            page = m.get("page_number")
            if method == "ocr" and src is not None and page is not None:
                seen_pages.add((src, page))
        ocr_pages_count = len(seen_pages)
    except Exception:
        # 忽略统计失败，不影响示例检索
        pass

    # 示例检索结果（带相似度分数）
    example_results = []
    try:
        results = vectorstore.similarity_search_with_score(question, k=top_k)
        for doc, score in results:
            example_results.append({
                "source_file": doc.metadata.get("source_file"),
                "page_number": doc.metadata.get("page_number"),
                "extraction_method": doc.metadata.get("extraction_method"),
                "similarity_score": float(score),
                "snippet": (doc.page_content[:300] if doc.page_content else None),
            })
    except Exception as e:
        example_results = [{"error": f"检索失败: {e}"}]

    summary = {
        "collection_count": collection_count,
        "ocr_pages_count": ocr_pages_count,
        "question": question,
        "top_k": top_k,
        "example_results": example_results,
    }

    out_dir = Path(settings.CHROMA_PERSIST_DIRECTORY)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "retrieval_verification.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return out_file


def main():
    parser = argparse.ArgumentParser(description="验证向量库检索并输出摘要")
    parser.add_argument("--question", default="什么是车险的免赔额？", help="检索问题")
    parser.add_argument("--k", "--top_k", dest="k", type=int, default=5, help="返回TopK结果")
    parser.add_argument("--quiet", "--log-only", dest="quiet", action="store_true", help="仅输出日志，关闭标准输出")
    args = parser.parse_args()

    # 修复日志初始化：setup_logging 接受 log_level 参数名
    setup_logging(log_level="INFO")
    out_file = run_verification(args.question, args.k)
    logger.info(f"检索验证摘要已写入: {out_file}")
    if not args.quiet:
        print(str(out_file))


if __name__ == "__main__":
    main()


