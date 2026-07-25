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

    # Attach browser-loadable URLs (chat-pdf selectedPdf.url pattern)
    samples_dir = Path("samples").resolve()
    pdf_dir = Path(settings.PDF_STORAGE_PATH).resolve()
    enriched: List[Dict[str, Any]] = []
    for doc in documents:
        item = dict(doc)
        name = item.get("name") or item.get("document_name") or ""
        path_str = item.get("path") or ""
        url = item.get("url")
        if not url and name:
            try:
                p = Path(path_str) if path_str else None
                if p and p.exists():
                    pref = str(p.resolve())
                    if pref.startswith(str(samples_dir)):
                        url = f"/samples/{name}"
                    elif pref.startswith(str(pdf_dir)):
                        url = f"/corpus-pdfs/{name}"
                if not url:
                    if (samples_dir / name).exists():
                        url = f"/samples/{name}"
                    elif (pdf_dir / name).exists():
                        url = f"/corpus-pdfs/{name}"
            except Exception:
                url = f"/samples/{name}" if name else None
        if url:
            item["url"] = url
        enriched.append(item)

    return {
        "documents": enriched,
        "chunk_count": chunk_count,
        "collection": collection,
        "pdf_storage_path": settings.PDF_STORAGE_PATH,
    }
