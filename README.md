# InsurIntellect Agent

**Insurance document Q&A with LLM + vector retrieval (FastAPI)**

[English](README.md) | [中文](README.zh-CN.md)

![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

Document Q&A stack for **insurance** materials: ingest PDFs / text into a vector store, answer with LLM + retrieval, FastAPI service surface under `app/`.

> Demo / research assistant — not regulated insurance advice.

## Why this exists

Policy PDFs are long and jargon-heavy. A retrieval-augmented agent is a practical portfolio slice of “LLM + domain docs” without claiming to be a carrier system.

## Features

- `ingest.py` document ingestion entry
- FastAPI app under `app/` (API + services + prompts)
- Optional extras in `requirements-optional.txt`
- Monitoring / reports folders for run artifacts

## Install

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
pip install -r requirements.txt
```

Configure model keys / vector backend via env as documented in `docs/` or `.env` examples if present.

## Usage

```bash
python ingest.py --help
uvicorn app.main:app --reload
```

## Project layout

```
app/
ingest.py
data/ logs/ reports/
tests/
```

## License

MIT. Free for commercial use with attribution. See [LICENSE](LICENSE).
