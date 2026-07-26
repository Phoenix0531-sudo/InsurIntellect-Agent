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
    # non-int document_id strings are preserved (ingest may use stem ids)
    assert out[0].document_id in (-1, "x")
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
        docs = data["documents"] or []
        if docs:
            # sample corpus should expose Chinese display names when present
            assert any(d.get("display_name") or d.get("name") for d in docs)


def test_curate_citations_filters_cover_and_dedupes():
    from app.services.query_service import QueryService

    svc = QueryService()
    raw = [
        {
            "document_name": "sample_critical_illness.pdf",
            "page_number": 1,
            "content": "文档名称：示例重大疾病保险条款\n产品名称：安康示例重大疾病保险\n文档类型：保险条款\n生效日期：2024-06-01",
            "similarity_score": 0.95,
        },
        {
            "document_name": "sample_critical_illness.pdf",
            "page_number": 2,
            "content": "第一条 等待期\n本合同自生效之日起，重大疾病保险金的等待期为 180 天。",
            "similarity_score": 0.2,
        },
        {
            "document_name": "sample_term_life.pdf",
            "page_number": 2,
            "content": "第二条 等待期\n自本合同生效之日起，被保险人因疾病导致的保险事故，等待期为 90 天。",
            "similarity_score": 0.21,
        },
        {
            "document_name": "sample_critical_illness.pdf",
            "page_number": 2,
            "content": "第一条 等待期\n本合同自生效之日起，重大疾病保险金的等待期为 180 天。",
            "similarity_score": 0.19,
        },
    ]
    out = svc.curate_citations(raw, "等待期是多久？", limit=4)
    assert 1 <= len(out) <= 4
    # cover page should not lead
    assert "等待期" in (out[0].get("content") or "")
    # same doc+page deduped
    keys = {(c.get("document_name"), c.get("page_number")) for c in out}
    assert len(keys) == len(out)



def test_public_citations_policy():
    from app.services.query_service import QueryService

    svc = QueryService()
    raw = [
        {
            "chunk_id": 1,
            "document_name": "sample_critical_illness.pdf",
            "content": "本合同等待期为九十天。等待期内出险不承担保险责任。",
            "page_number": 2,
            "similarity_score": 0.81,
        },
        {
            "chunk_id": 2,
            "document_name": "sample_critical_illness.pdf",
            "content": "文档名称：示例\n产品名称：演示\n状态：演示样本",
            "page_number": 1,
            "similarity_score": 0.05,
        },
        {
            "chunk_id": 3,
            "document_name": "pad.pdf",
            "content": "filler",
            "page_number": 1,
            "similarity_score": 0.0,
        },
    ]
    pub = svc.public_citations(raw)
    assert all(float(c.get("similarity_score") or 0) > 0 for c in pub)
    assert all(c.get("chunk_id") != 3 for c in pub)

    assert svc.citations_for_kind("refusal", raw) == []
    assert svc.citations_for_kind("advice", raw) == []
    assert svc.citations_for_kind("degraded", raw) == []
    ans = svc.citations_for_kind("answer", raw)
    assert len(ans) >= 1
    assert all(float(c.get("similarity_score") or 0) > 0 for c in ans)


def test_advice_and_offtopic_helpers():
    from app.services.query_service import QueryService

    svc = QueryService()
    assert svc._is_advice_or_guarantee_question("这份保单保证我一定能获赔吗？")
    assert svc._is_off_topic("今天北京天气怎么样？", [])
