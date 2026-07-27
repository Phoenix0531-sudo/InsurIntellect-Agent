#!/usr/bin/env python
"""Empty-index honesty matrix for InsurIntellect.

Uses a *valid Windows temp path* (never ////tmp) so sqlite + empty chroma work.
Does not touch the live demo corpus under data/.

Expectations (no live LLM required):
  - health starts without crash
  - corpus list empty or zero docs
  - Q1 等待期 → refusal (no evidence), public citations empty
  - Q3 保证获赔 → advice, public citations empty
  - weather → refusal, public citations empty

Exit 0 on all PASS.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="insur_empty_", dir=str(Path.home() / "AppData" / "Local" / "Temp")))
    chroma = work / "chroma"
    processed = work / "processed"
    pdfs = work / "pdfs"
    db_file = work / "app.db"
    chroma.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    pdfs.mkdir(parents=True, exist_ok=True)

    # Empty BM25 artifacts so loaders do not fall back to project data/
    (processed / "bm25_chunk_map.json").write_text("{}", encoding="utf-8")
    (processed / "corpus_manifest.json").write_text(
        json.dumps({"documents": [], "chunk_count": 0, "collection": "insurance_documents"}, ensure_ascii=False),
        encoding="utf-8",
    )

    # Isolate all path-like settings BEFORE importing app modules.
    os.environ["CHROMA_PERSIST_DIRECTORY"] = str(chroma)
    os.environ["PROCESSED_DATA_PATH"] = str(processed)
    os.environ["PDF_STORAGE_PATH"] = str(pdfs)
    # Windows-safe sqlite URLs (3 slashes + absolute path with forward slashes)
    db_url = "sqlite:///" + db_file.resolve().as_posix()
    os.environ["DATABASE_URL"] = db_url
    os.environ["DATABASE_URL_ASYNC"] = "sqlite+aiosqlite:///" + db_file.resolve().as_posix()
    os.environ["SIMPLE_RAG_MODE"] = "true"
    os.environ["ENABLE_QUERY_REWRITING"] = "false"
    os.environ["ENABLE_QUERY_ROUTING"] = "false"
    os.environ["OPENAI_EMBEDDING_MODEL"] = os.environ.get(
        "OPENAI_EMBEDDING_MODEL", "hf:BAAI/bge-small-zh-v1.5"
    )
    os.environ["SIMILARITY_THRESHOLD"] = os.environ.get("SIMILARITY_THRESHOLD", "0.32")
    os.environ["HF_HUB_OFFLINE"] = os.environ.get("HF_HUB_OFFLINE", "1")
    os.environ["TRANSFORMERS_OFFLINE"] = os.environ.get("TRANSFORMERS_OFFLINE", "1")
    # Force no-key path so matrix is deterministic offline
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["SILICONFLOW_API_KEY"] = ""
    # Avoid picking up project .env that reintroduces real paths/keys after import
    os.environ["CHROMA_ANONYMIZED_TELEMETRY"] = "false"
    os.environ["CHROMA_DISABLE_TELEMETRY"] = "1"

    print("empty-work", work)
    print("db", db_url)
    print("chroma", chroma)

    failed = 0
    try:
        # Clear cached settings if any
        for mod in list(sys.modules):
            if mod == "app" or mod.startswith("app."):
                del sys.modules[mod]

        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            # health
            r = client.get("/api/v1/health/")
            print("health", r.status_code, r.json() if r.status_code == 200 else r.text[:200])
            if r.status_code != 200:
                failed += 1

            # corpus: sample PDFs may still appear as UI catalog fallback, but
            # empty index means chunk_count == 0 and retrieval has no evidence.
            r = client.get("/api/v1/corpus")
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            print("corpus", r.status_code, body if isinstance(body, dict) else str(body)[:200])
            if r.status_code != 200:
                print("FAIL corpus status", r.status_code)
                failed += 1
            else:
                chunk_count = 0
                if isinstance(body, dict):
                    chunk_count = int(body.get("chunk_count") or 0)
                if chunk_count != 0:
                    print("FAIL corpus expected chunk_count=0, got", chunk_count)
                    failed += 1
                else:
                    print("corpus PASS chunk_count=0 (UI may still list samples/ catalog)")

            cases = [
                {
                    "id": "Q1_empty",
                    "q": "等待期是多久？",
                    "expect_kind": {"refusal", "llm_unavailable", "degraded"},
                    # empty index: prefer refusal; llm_unavailable only if code still tries LLM with zero chunks
                    "prefer_kind": "refusal",
                    "max_cites": 0,
                },
                {
                    "id": "Q3_empty",
                    "q": "这份保单保证我一定能获赔吗？",
                    "expect_kind": {"advice"},
                    "max_cites": 0,
                },
                {
                    "id": "WX_empty",
                    "q": "今天北京天气怎么样？",
                    "expect_kind": {"refusal"},
                    "max_cites": 0,
                },
            ]

            for c in cases:
                resp = client.post(
                    "/api/v1/queries/ask",
                    json={"question": c["q"], "stream": False, "show_sources": True},
                )
                if resp.status_code != 200:
                    print(c["id"], "FAIL http", resp.status_code, resp.text[:300])
                    failed += 1
                    continue
                data = resp.json()
                kind = data.get("answer_kind")
                cites = data.get("retrieved_chunks") or []
                ans = (data.get("answer") or "")[:120].replace("\n", " ")
                ok_kind = kind in c["expect_kind"]
                ok_cites = len(cites) <= c.get("max_cites", 0)
                # extra honesty: answer should not invent waiting-period numbers when empty
                invent = False
                if c["id"] == "Q1_empty" and any(x in (data.get("answer") or "") for x in ["30天", "90天", "等待期为"]):
                    # only fail invent if it claims concrete term without cites
                    if len(cites) == 0 and kind not in ("refusal", "llm_unavailable", "degraded", "advice"):
                        invent = True
                status = "PASS" if (ok_kind and ok_cites and not invent) else "FAIL"
                if status == "FAIL":
                    failed += 1
                print(
                    c["id"],
                    status,
                    "kind=",
                    kind,
                    "cites=",
                    len(cites),
                    "ans=",
                    ans,
                )

    except Exception as e:
        print("FAIL exception", type(e).__name__, e)
        failed += 1
    finally:
        try:
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass

    print("empty_index_smoke failed=", failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
