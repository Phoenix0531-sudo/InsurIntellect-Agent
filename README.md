# InsurIntellect Agent

**Insurance clause RAG (local PDF corpus → hybrid retrieve → cited answers).**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Local demo for **clause-grounded** Q&A over insurance-like PDFs.  
**Not regulated insurance advice.** Not a multi-tenant SaaS, not a licensed advisor, not an agent orchestration platform.

## Preview

![InsurIntellect clause RAG UI](docs/screenshots/preview.png)

Left: indexed documents + example questions. Right: structured answer with citation cards (document / page / excerpt).

## Architecture

```
samples/*.pdf  ──generate──►  data/documents/pdfs
        │
        ▼
 simple_ingest.py  ──►  Chroma (vectors) + BM25/jieba + corpus_manifest
        │
        ▼
 POST /api/v1/queries/ask
   retrieve top-k (hybrid) → refuse if weak/off-topic/advice
   → LLM (OpenAI-compatible) structured answer with [1][2] citations
        │
        ▼
 static/ UI (light, two-pane, sources first-class)
```

Default main path is **SIMPLE_RAG_MODE**: retrieve → generate.  
Query rewriting, SQL routing, KG injection, and regulatory multi-agent chains stay off unless you opt in.

## Quickstart (uv)

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent

uv venv .venv --python 3.11
# Windows: .venv\Scripts\activate
source .venv/bin/activate   # or Scripts on Windows
uv pip install -r requirements.txt
uv pip install pytest ruff httpx

cp .env.example .env
# set OPENAI_BASE_URL / OPENAI_API_KEY for your OpenAI-compatible gateway
# preferred: local HF embedding (cached after first download)
# OPENAI_EMBEDDING_MODEL=hf:BAAI/bge-small-zh-v1.5
# offline fallback: OPENAI_EMBEDDING_MODEL=local:hash  (re-ingest after switch)

# sample corpus (public fake clauses, not real policies)
uv run python scripts/generate_sample_corpus.py --copy-to-data
uv run python scripts/simple_ingest.py --reset

# serve
export HOST=127.0.0.1 PORT=8766
uv run uvicorn app.main:app --host 127.0.0.1 --port 8766
# open http://127.0.0.1:8766/
```

Provider note: portfolio demos prefer a local **new-api** (or any OpenAI-compatible) endpoint.  
If the key is missing, the API still returns retrieved chunks with an honest **LLM unavailable** message.

## Demo questions

| ID | Question | Expectation |
|----|----------|-------------|
| Q1 | 等待期是多久？ | Cited answer from sample clauses (e.g. 90 / 180 days) |
| Q2 | 责任免除包括哪些情形？ | Multi-point exclusions with citations |
| Q3 | 这份保单保证我一定能获赔吗？ | Hard boundary / refuse purchase-or-guarantee advice |

## API

- `GET /api/v1/health/`
- `GET /api/v1/corpus`
- `POST /api/v1/queries/ask` body: `{ "question": "...", "stream": false }`  
  Response includes `answer`, `retrieved_chunks[]` (`document_name`, `page_number`, `content`, `similarity_score`).

## Tests & CI

```bash
uv run ruff check . --select E9,F63,F7,F82
uv run pytest -q tests
```

CI runs the same critical ruff select set + `pytest tests/` without requiring live LLM keys.

## Scope

**In**

- Local PDF clause corpus, hybrid retrieval, cited answers, refuse/degrade paths
- Static two-pane UI focused on document evidence

**Out**

- Regulated advice, guaranteed claim outcomes, multi-tenant auth, full PDF.js reader
- Productized text-to-SQL / knowledge-graph UI (code may exist as advanced/off by default)

## License

MIT. See [LICENSE](LICENSE).
