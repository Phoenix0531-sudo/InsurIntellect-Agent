"""Corpus listing for UI document pane."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

from app.core.config import settings
from app.core.app_logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("", summary="List indexed corpus documents")
@router.get("/", summary="List indexed corpus documents")
async def list_corpus() -> Dict[str, Any]:
    """Return sample/indexed document list for the left pane."""
    processed = Path(settings.PROCESSED_DATA_PATH)
    manifest_path = processed / "corpus_manifest.json"
    documents: List[Dict[str, Any]] = []
    chunk_count = 0
    collection = "insurance_documents"

    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            documents = data.get("documents") or []
            chunk_count = int(data.get("chunk_count") or 0)
            collection = data.get("collection") or collection
        except Exception as e:
            logger.warning(f"read corpus_manifest failed: {e}")

    if not documents:
        pdf_dir = Path(settings.PDF_STORAGE_PATH)
        if pdf_dir.exists():
            for p in sorted(pdf_dir.glob("*.pdf")):
                documents.append({"name": p.name, "path": str(p), "pages": None})
        samples = Path("samples")
        if samples.exists():
            for p in sorted(samples.glob("*.pdf")):
                if not any(d.get("name") == p.name for d in documents):
                    documents.append({"name": p.name, "path": str(p), "pages": None})

    # BM25 map size as fallback chunk count
    if not chunk_count:
        bm25_map = processed / "bm25_chunk_map.json"
        if bm25_map.exists():
            try:
                chunk_count = len(json.loads(bm25_map.read_text(encoding="utf-8")))
            except Exception:
                pass

    return {
        "documents": documents,
        "chunk_count": chunk_count,
        "collection": collection,
        "pdf_storage_path": settings.PDF_STORAGE_PATH,
    }
