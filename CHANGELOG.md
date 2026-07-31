# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-07-30

### Added
- Sample insurance clause PDFs (`samples/*.pdf`) with verbatim clause language for reproducible demo
- `scripts/generate_sample_corpus.py` for one-click regeneration of de-identified sample policies
- Refusal gate for purchase/guarantee questions and off-topic queries (insurance vertical guardrail)
- LLM-unavailable degraded path with chunk preview citations
- SSE streaming path (`POST /api/v1/queries/ask` with `stream=true`) with structured `start / context / token / end` events
- `clauses` corpus manifest feed for the left sidebar document list
- Real demo screenshots: preview, citations, refuse-advice, empty corpus (no AI mock-ups)
- Repo hygiene test (`tests/test_project_hygiene.py`) enforcing pyproject-based metadata

### Changed
- Reconstructed missing `app/models` package (`schemas.py`, `database_models.py`, `__init__.py`)
- Migrated project metadata to `pyproject.toml`; `setup.py` retained only for editable installs
- Dockerfile rebuilt as multi-stage (`deps` + `runtime`), `--no-compile`, `[IP]` healthcheck
- README rewritten in FinRobot-style layout (EN + zh-CN) with real screenshots, no emoji in body
- Citation, refusal, response-shaping, and query-history logic extracted into dedicated modules
- Main query path slimmed to `retrieve -> refuse-or-summarize -> answer with citations`
- Default provider switched from SiliconFlow to local new-api (OpenAI-compatible gateway)
- Stripped ~10 dead config fields (regulatory/rerank-tuning, security/JWT, metrics, upload quota)
  so `Settings` surfaces only what the live path actually reads

### Removed
- ~925 lines of unreachable advanced paths (`stream_query`, `build_context` sync, `answer()`,
  `run_lead_reviewer`/`run_report_author`/`_dynamic_ranking`, regulatory reranker family)
- `app/services/document_parser_service.py` (319 lines) — was the only consumer of the
  `unstructured` / `pdfplumber` / `pytesseract` stack; no live ingestion code mentions it
- `app/core/timeliness.py` (127 lines) — `compute_timeliness_score` last call site was inside
  the deleted `_dynamic_ranking` method; module relied on `settings.TIMELINESS_*` fields that
  were never declared in `config.py`
- `app/core/ingestion_config.yml` (106 lines) — 0 importers, never loaded by any Python path
- `requirements-advanced.txt` plus `pyproject.toml` `[advanced]` / `[all]` extras — depend on
  packages that no longer appear anywhere in `app/`, `tests/`, or `scripts/`
- Redundant `static/js/script.js`; frontend consolidated to a single `static/js/app.js` entry
- Logo SVG and other unused files; replaced by GPT-generated PNG mascot
- Unused `scikit-learn` dependency (~150 MB Docker image savings)
- Dead `egg-info` artifact from working tree (gitignored)
- Stray root file `-` (6555-byte backfill report JSON, miscommitted on 6月 8)

### Fixed
- `sqlalchemy.ext.declarative.declarative_base` deprecation warning
- jieba / starlette / pkg_resources pytest warnings silenced via `filterwarnings`
- Structured logger now flushes file handlers on shutdown

## [1.0.0] - 2026-06-08

### Added
- Initial public release
- feat: 初始化项目基础架构和核心功能
