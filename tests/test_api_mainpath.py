"""API / schema smoke tests (no external LLM required)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_models_import():
    from app.models.schemas import QueryRequest, QueryResponse, RetrievedChunk, HealthCheck
    from app.models.database_models import QueryHistory, Document, DocumentChunk

    assert QueryRequest(question="等待期是多久？").question
    chunk = RetrievedChunk(
        chunk_id=1,
        document_id=1,
        document_name="sample_term_life.pdf",
        content="等待期为 90 天",
        page_number=2,
        similarity_score=0.8,
    )
    resp = QueryResponse(
        question="q",
        answer="a",
        query_type="general",
        response_time=0.1,
        chunks_used=1,
        retrieved_chunks=[chunk],
        confidence_score=0.8,
    )
    assert resp.chunks_used == 1
    assert HealthCheck(status="healthy", database_status=True, vector_db_status=True, llm_status=True)
    assert QueryHistory.__tablename__ == "query_history"
    assert Document.__tablename__ == "documents"
    assert DocumentChunk.__tablename__ == "document_chunks"


def test_retrieved_chunk_schema_norm():
    from app.services.query_service import QueryService

    svc = QueryService()
    raw = [
        {
            "chunk_id": "12",
            "document_id": "x",
            "document_name": None,
            "content": "责任免除：酒驾",
            "page_number": "3",
            "similarity_score": 1.2,
            "metadata": {"filename": "sample_term_life.pdf"},
        }
    ]
    out = svc._to_retrieved_chunks(raw)
    assert len(out) == 1
    assert out[0].chunk_id == 12
    assert out[0].document_id == -1
    assert out[0].document_name == "sample_term_life.pdf"
    assert out[0].page_number == 3
    assert 0.0 <= out[0].similarity_score <= 1.0


def test_health_endpoint():
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/api/v1/health/")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "database_status" in data


def test_ask_validation_empty_question():
    from app.main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/v1/queries/ask",
            json={"question": "   ", "stream": False},
        )
        assert r.status_code == 400


def test_corpus_endpoint():
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/api/v1/corpus")
        assert r.status_code == 200
        data = r.json()
        assert "documents" in data
