# InsurIntellect Agent

**Insurance document Q&A with LLM + vector retrieval on FastAPI.**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Ingest, retrieve, answer. Demo / research assistant only.

## Preview

![InsurIntellect Agent](docs/screenshots/preview.png)

## Features

- PDF / text ingestion into a vector store
- Retrieval-grounded LLM answers
- FastAPI surface under app/
- Ingest scripts plus monitoring / report folders
- Hard CI (critical ruff + pytest)

## Get started

### Install

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
pip install -r requirements.txt
```

### Usage

```bash
python ingest.py --help
uvicorn app.main:app --reload
pytest tests/
```

## Project layout

```
app/  ingest.py
data/ logs/ reports/ monitoring/
tests/
```

## Notes

Not regulated insurance advice and not a carrier production system.

## License

MIT. Free for commercial use with attribution where applicable. See [LICENSE](LICENSE).
