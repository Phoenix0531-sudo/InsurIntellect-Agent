# InsurIntellect Agent

**Insurance document Q&A with LLM + vector retrieval over FastAPI.**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Insurance document Q&A with LLM + vector retrieval over FastAPI.

Ingest → retrieve → answer. Demo / research assistant.


## Features

- 📚 PDF / text ingestion into a vector store
- 🧠 LLM answers grounded by retrieval
- 🚀 FastAPI surface under `app/`
- 🧰 Scripts for ingest + monitoring / report folders
- ✅ Hard CI (critical ruff + pytest)

## Get started

### Install

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
pip install -r requirements.txt
# configure model keys / vector backend via env
```

### Usage

```bash
python ingest.py --help
uvicorn app.main:app --reload
pytest tests/
```

> Not regulated insurance advice.

## Project layout

```
app/  ingest.py
data/ logs/ reports/ monitoring/
tests/
```

## Notes

Portfolio slice of “LLM + domain PDFs”, not a carrier production system.

## License

MIT. Free for commercial use with attribution where applicable. See [LICENSE](LICENSE).
