# InsurIntellect Agent

**Insurance-document Q&A: PDF ingest → chunk/embed → Chroma + BM25 hybrid retrieval → FastAPI answers.**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Demo / research assistant for domain PDFs. **Not regulated insurance advice** and not a carrier production system.

## Preview

![InsurIntellect Agent](docs/screenshots/preview.png)

## Two-phase pipeline

### 1) Ingest (`ingest.py`)

Documented responsibilities in the script header:

- Read PDFs from the configured directory
- Optional AI metadata extraction from snippets
- LangChain-style chunking
- Build local **Chroma** vector store with embeddings
- **BM25Plus + jieba** for Chinese lexical retrieval alongside vectors

### 2) Serve (`app/`)

```
app/
  main.py           # FastAPI entry
  api/              # routes
  services/         # query_service (retrieve + LLM; stream uses llm_core / llm_light)
  core/ data/ prompts.py
```

Query path: retrieve top chunks → compose prompt → LLM answer (streaming supported). Hard CI catches undefined names in the stream path.

## Install

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
pip install -r requirements.txt
# optional extras: requirements-optional.txt
# configure model keys / paths via env — never commit secrets
```

## Run

```bash
python ingest.py --help
# after corpus is indexed:
uvicorn app.main:app --reload
pytest tests/
```

## Scope

- **In:** local RAG over insurance-like PDFs, hybrid retrieval, FastAPI Q&A, monitoring/report folders
- **Out:** licensed advice, guaranteed legal correctness, multi-tenant SaaS

## License

MIT. See [LICENSE](LICENSE).
