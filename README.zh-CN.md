# InsurIntellect Agent

**开源保险条款智能体：本地语料、可追溯引用、诚实拒答。**

[English](README.md) | [中文](README.zh-CN.md)

<!-- 动态 GitHub 徽章（仓库已公开） -->
[![CI](https://img.shields.io/github/actions/workflow/status/Phoenix0531-sudo/InsurIntellect-Agent/ci.yml?branch=master&label=CI)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/Phoenix0531-sudo/InsurIntellect-Agent)](LICENSE)
[![Stars](https://img.shields.io/github/stars/Phoenix0531-sudo/InsurIntellect-Agent?style=flat)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/Phoenix0531-sudo/InsurIntellect-Agent/master)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/commits/master)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)](#快速开始)

<!-- 产品 / 栈（诚实静态 — 不造假 PyPI / Discord / Downloads） -->
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Chroma](https://img.shields.io/badge/vector-Chroma-FF6F61.svg)](https://www.trychroma.com/)
[![BM25](https://img.shields.io/badge/lexical-BM25%2Bjieba-6C63FF.svg)](#架构)
[![Embedding](https://img.shields.io/badge/embed-BGE%20small%20zh-orange.svg)](#提供商说明)
[![Threshold](https://img.shields.io/badge/SIMILARITY__THRESHOLD-0.32-informational.svg)](#提供商说明)
[![Port](https://img.shields.io/badge/demo-localhost%3A8766-0ea5e9.svg)](#快速开始)
[![Mode](https://img.shields.io/badge/SIMPLE__RAG-default-success.svg)](#架构)
[![UI](https://img.shields.io/badge/UI-static%20HTML%2FCSS%2FJS-lightgrey.svg)](#预览)
[![Not advice](https://img.shields.io/badge/Not%20regulated%20insurance%20advice-critical.svg)](#免责声明)

![Visitors](https://visitor-badge.laobi.icu/badge?page_id=Phoenix0531-sudo.InsurIntellect-Agent&left_color=gray&right_color=%231D9CFF)

<p align="center">
  <img src="docs/screenshots/logo.png" alt="InsurIntellect 标识" width="72" />
</p>

<p align="center">
  <img src="docs/screenshots/hero.png" alt="InsurIntellect 主视觉 — 双栏条款 RAG" width="92%" />
</p>
<p align="center"><sub>主视觉来自真实双栏会话（右栏引用、左栏条款 PDF / 证据条）。</sub></p>

<details>
<summary><strong>四态界面</strong>（主界面 · 引用 · 拒答/建议 · 空态）</summary>
<p align="center">
  <img src="docs/screenshots/preview.png" alt="主界面双栏" width="48%" />
  <img src="docs/screenshots/citations.png" alt="引用卡" width="48%" />
</p>
<p align="center">
  <img src="docs/screenshots/refuse_advice.png" alt="拒答 / 建议边界" width="48%" />
  <img src="docs/screenshots/preview_empty.png" alt="冷启动 / 空态" width="48%" />
</p>
</details>

InsurIntellect 是面向作品集的 **金融垂直智能体演示**：对保险条款 / 保单类 PDF 做本地问答。

- 索引本地条款语料
- 混合检索（向量 + BM25）
- 只基于 **可追溯引用** 作答
- 对购保建议、保证理赔、离题问题 **拒答 / 强边界**

它 **不是** 多租户 SaaS，**不是** Agent 画布平台，**不构成受监管保险建议（Not regulated insurance advice）**。

产品叙事对齐金融智能体同侪 [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)（智能体 + 证据溯源）。证据 UI 采用轻量 RAGFlow 式「知识库 + 引用」布局。免责语气参考 [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)。

---

## 目录

- [为什么做 InsurIntellect](#为什么做-insurintellect)
- [设计原则](#设计原则)
- [预览](#预览)
- [架构](#架构)
- [核心能力](#核心能力)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [固定演示问题](#固定演示问题)
- [API](#api)
- [主路径目录](#主路径目录)
- [测试与 CI](#测试与-ci)
- [范围](#范围)
- [提供商说明](#提供商说明)
- [免责声明](#免责声明)
- [许可](#许可)
- [相关阅读](#相关阅读仅结构灵感)

---

## 为什么做 InsurIntellect

1. **保险文本高风险。** 通用聊天会编造等待期与责任免除。本演示 **用检索门闩约束回答**，有答则展示 **文档 / 页码 / 摘录**。
2. **溯源优先于花活。** 对齐 FinRobot「数字由代码算、叙述由 LLM 写」：这里是 **条款由检索给出、叙述由 LLM 辅助、证据不足就拒答**。
3. **作品集诚实范围。** 只做一条垂直主路径（本地 PDF → hybrid 检索 → 带引用回答 / 拒答）。不做假多租户 SaaS，不做股权研究多 Agent 套壳，不做「保证获赔」机器人。
4. **可复现演示。** 公开合成样例、`run_demo` 强制 BGE + 阈值、固定 smoke（Q1/Q2/Q3/天气）、CI 不依赖在线 LLM Key。

---

## 设计原则

核心是 **检索证据** 与 **LLM 叙述** 严格分离：

```text
条款来自已入库语料的检索。
叙述由 LLM 辅助生成（OpenAI 兼容网关）。
每条回答要么带引用，要么拒答。
```

| 层 | 做什么 | 不做什么 |
|----|--------|----------|
| **语料 / 入库** | PDF 切块、嵌入、BM25 + Chroma | 编造条款原文 |
| **检索** | Hybrid top-k、分数门闩 | 保证理赔结果 |
| **生成** | 结论 / 依据 / 边界 + `[1][2]` | 给出购买或核保建议 |
| **对外引用** | 有据回答展示真实得分 chunk | 拒答 / 建议类不展示填充引用 |

证据不足、离题、或用户索取受监管建议时：返回 **拒答 / 边界**，并保持 **对外 citations 为空**。

---

## 预览

![InsurIntellect 条款 RAG 界面](docs/screenshots/preview.png)

| 视图 | 文件 |
|------|------|
| 主界面双栏 | [docs/screenshots/preview.png](docs/screenshots/preview.png) |
| 引用卡 | [docs/screenshots/citations.png](docs/screenshots/citations.png) |
| 拒答 / 建议边界 | [docs/screenshots/refuse_advice.png](docs/screenshots/refuse_advice.png) |
| 冷启动 / 空态 | [docs/screenshots/preview_empty.png](docs/screenshots/preview_empty.png) |

左栏：产品名、已索引文档、示例问题、免责。  
右栏：对话、结构化答案、引用卡（文档名 / 页码 / 摘录）。  
UI 壳为静态 HTML/CSS/JS（ChatPDF 式双栏，主色 `#1D9CFF`）；产品故事是保险条款 RAG，不是通用 PDF Chat。

---

## 架构

```text
samples/*.pdf  ──生成──►  data/documents/pdfs
        │
        ▼
 simple_ingest.py
   → Chroma（向量）+ BM25/jieba + corpus_manifest
        │
        ▼
 POST /api/v1/queries/ask
   hybrid 检索 top-k
   → 门闩：低分 / 离题 / 购保建议  →  拒答（citations 为空）
   → 否则 LLM 结构化回答 + [1][2] + public_citations
        │
        ▼
 static/ UI  ·  默认浅色  ·  引用一等公民
```

默认 **`SIMPLE_RAG_MODE=true`**：retrieve → generate。

默认关闭（仅 advanced 可选）：查询重写、SQL 路由、知识图谱注入、监管多 Agent 长链。

### 回答类型 `answer_kind`

| 值 | 含义 | 对外 `retrieved_chunks` |
|----|------|-------------------------|
| `answer` | 有据条款问答 | 真实得分引用 |
| `refusal` | 离题 / 证据不足 | 空 |
| `advice` | 购买 / 保证理赔 /「该不该买」 | 空 |
| `llm_unavailable` | 无 Key 或 LLM 失败；检索仍可进行 | 诚实降级策略 |
| `degraded` | 超时 / 部分路径 | 尽力返回 + 诚实文案 |

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 条款语料优先 | 仓库仅公开假样例 PDF，不提交真实客户保单 |
| 混合检索 | Chroma + BM25/jieba；默认嵌入 `hf:BAAI/bge-small-zh-v1.5` |
| 分数门闩 | BGE 下 `SIMILARITY_THRESHOLD=0.32`（demo 脚本强制） |
| 带引用回答 | 结论 / 条款依据 / 边界 + 一行免责 |
| 诚实拒答 | 天气、购保建议、「保证获赔」→ 边界，不当闲聊 |
| 对外引用策略 | answer 保留真实得分；refuse/advice → `[]` |
| 证据 UI | 双栏、引用卡、可点 `[n]`、状态 pill |
| 本地优先 | `uv` + **127.0.0.1:8766**；OpenAI 兼容网关 |

---

## 技术栈

| 层 | 选型 |
|----|------|
| API | FastAPI + Uvicorn |
| 检索 | Chroma + BM25/jieba hybrid |
| 嵌入 | 本机 HF `BAAI/bge-small-zh-v1.5`（或离线 `local:hash`） |
| LLM | OpenAI 兼容（`OPENAI_BASE_URL`） |
| UI | 静态 HTML / CSS / JS（`static/js/app.js`） |
| 测试 | pytest + ruff critical（CI） |
| 演示 | `scripts/run_demo.sh` / `.bat` + `demo_smoke.py` |

---

## 快速开始

### 1. 克隆与环境

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent

uv venv .venv --python 3.11
# Windows: .venv\Scripts\activate
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install pytest ruff httpx

cp .env.example .env
# 填写 OPENAI_BASE_URL / OPENAI_API_KEY（OpenAI 兼容网关）
# 推荐嵌入（入库与查询必须一致）：
# OPENAI_EMBEDDING_MODEL=hf:BAAI/bge-small-zh-v1.5
# SIMILARITY_THRESHOLD=0.32
# 离线回退：OPENAI_EMBEDDING_MODEL=local:hash（切换后必须重新 ingest）
```

### 2. 样例语料与入库

```bash
uv run python scripts/generate_sample_corpus.py --copy-to-data
uv run python scripts/simple_ingest.py --reset
```

样例为 **公开合成条款**（等待期、责任免除、犹豫期等），不是真实保单。

### 3. 一键演示服务

Shell 环境可能污染 `.env`。优先用 demo 启动脚本（会 **再次强制** BGE + 阈值）：

```bash
bash scripts/run_demo.sh
# Windows: scripts\run_demo.bat
```

或手动：

```bash
export HOST=127.0.0.1 PORT=8766
export OPENAI_EMBEDDING_MODEL=hf:BAAI/bge-small-zh-v1.5
export SIMILARITY_THRESHOLD=0.32
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export SIMPLE_RAG_MODE=true
uv run uvicorn app.main:app --host 127.0.0.1 --port 8766
```

浏览器：**http://127.0.0.1:8766/**  
OpenAPI（`DEBUG=true` 时）：**http://127.0.0.1:8766/docs**

无 API Key 时：接口走诚实的 **LLM 不可用** 路径，不静默编造保障范围。

### 4. 固定回归（服务需已启动）

```bash
# Linux/macOS/git-bash
.venv/bin/python scripts/demo_smoke.py
# Windows
.venv\Scripts\python.exe scripts\demo_smoke.py
```

覆盖 Q1 / Q2 / Q3 / 离题天气，并检查 `answer_kind` 与引用诚实性。

可选空索引诚实矩阵（Windows 合法临时目录，不碰正式语料）：

```bash
.venv\Scripts\python.exe scripts\empty_index_smoke.py
```

---

## 固定演示问题

| ID | 问题 | 期望 |
|----|------|------|
| Q1 | 等待期是多久？ | 样例条款有据回答（`answer`，≥1 条引用） |
| Q2 | 责任免除包括哪些情形？ | 多点列举 + 引用 |
| Q3 | 这份保单保证我一定能获赔吗？ | `advice` 边界；**对外 citations 为空** |
| WX | 今天北京天气怎么样？ | `refusal`；**对外 citations 为空** |

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health/` | 数据库 / 向量库 / LLM 状态 |
| `GET` | `/api/v1/corpus` | 左栏文档列表 |
| `POST` | `/api/v1/queries/ask` | Body：`{ "question": "...", "stream": false }` |

稳定字段：`question`、`answer`、`answer_kind`、`retrieved_chunks[]`（`document_name`、`page_number`、`content`、`similarity_score`）、`chunks_used`、`confidence_score`、`response_time`。

流式：同一 `POST` 且 `"stream": true`（SSE）；终态事件与非流式同一套引用策略。

示例：

```bash
curl -s http://127.0.0.1:8766/api/v1/queries/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"等待期是多久？","stream":false}'
```

---

## 主路径目录

```text
InsurIntellect-Agent
├── app/
│   ├── main.py                 # FastAPI 入口、静态挂载
│   ├── api/                    # /health /queries /corpus
│   ├── core/                   # config、fusion、rag_workflow（检索后端）
│   ├── models/                 # schemas + 轻量 DB 模型
│   ├── services/
│   │   ├── query_service.py    # SIMPLE 路径、拒答、public_citations
│   │   ├── embedding_service.py
│   │   └── llm_service.py
│   └── prompts.py
├── static/                     # 双栏 UI（主 JS：js/app.js）
├── scripts/                    # 仅主路径
│   ├── generate_sample_corpus.py
│   ├── simple_ingest.py
│   ├── run_demo.sh / run_demo.bat
│   ├── demo_smoke.py
│   ├── capture_ui_states.py
│   └── empty_index_smoke.py    # 可选：空索引诚实矩阵
├── samples/                    # 公开假 PDF 源
├── tools/insurance_ontology.json  # 可选 advanced 重写数据
├── tests/                      # CI 不依赖真实 LLM Key
├── docs/screenshots/
├── .env.example
└── requirements.txt
```

---

## 测试与 CI

```bash
uv run ruff check . --select E9,F63,F7,F82
uv run pytest -q tests
```

GitHub Actions 跑同一套 critical ruff + `pytest tests/`，**不要求** 在线 LLM 或嵌入 API Key。

工作流： [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

---

## 范围

**做**

- 本地保险类 PDF 语料
- 混合检索 + 带引用回答
- 拒答 / 建议边界 / LLM 降级诚实
- 端口 8766 的静态证据 UI

**不做**

- 持牌销售 / 理赔承诺
- 多租户登录 / SaaS 上传产品化
- 完整 PDF 阅读器作为一期硬需求（资源可能用于高亮演示）
- 产品化 text-to-SQL / KG / 多 Agent 编排 UI

Docker（`Dockerfile`，默认 8000）可选。作品集演示优先 **uv + 8766**。

---

## 提供商说明

- **LLM**：任意 OpenAI 兼容 Base URL（作品集默认本机 new-api，如 `http://127.0.0.1:31876/v1`）。禁止提交密钥。
- **嵌入**：默认本机 HF `BAAI/bge-small-zh-v1.5`（缓存后本地免费）。**入库与查询必须同一模型**；换模型后执行 `simple_ingest.py --reset`。
- **Hash 回退** `local:hash` 仅适合离线演示，排序较弱——仅在明确使用 hash 时再调低阈值。

---

## 免责声明

本仓库代码与样例文档按 **MIT** 许可发布，仅供 **演示与研究**。不得视为保险销售、核保、理赔处理或受监管金融建议。任何保险决策前，请咨询合格专业人士并核对官方保单条款。

**Not regulated insurance advice. 不构成受监管保险建议。**

---

## 许可

MIT，见 [LICENSE](LICENSE)。

---

## 相关阅读（仅结构灵感）

- [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) — 金融 AI Agent 平台；溯源 / 智能体产品叙事（本 README 主骨架）
- [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) — 开源金融 LLM 生态；Why + 免责写法
- [RAGFlow](https://github.com/infiniflow/ragflow) — 通用 RAG 引擎；知识库 + 引用产品形态（非保险垂直）
