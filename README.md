<div align="center">

# InsurIntellect Agent · 保险智能问答系统

**Intelligent Insurance Document Q&A System Powered by LLM and Vector Retrieval**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](setup.py)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.2+-blue?logo=langchain)](https://www.langchain.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5+-yellow)](https://www.trychroma.com)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)](.)

</div>

---

## 项目简介 | Overview

在保险行业，大量产品条款、监管文件、理赔规则以 PDF 形式分散存储，业务人员难以快速检索和精准问答。InsurIntellect Agent 通过 RAG（检索增强生成）技术，将非结构化保险文档转化为可交互的知识库，支持语义检索、多轮对话、流式输出与监管感知重排序。

> Insurance documents — policy terms, regulatory filings, claims rules — are scattered across thousands of PDFs. InsurIntellect Agent unlocks this knowledge by combining vector retrieval with large language models, providing precise semantic search, multi-turn conversation, streaming output, and regulatory-aware re-ranking in one unified system.

---

## 技术特性 | Technical Highlights

| 特性 | Feature | 说明 |
|------|---------|------|
| **RAG 工作流** | RAG Pipeline | 查询改写 -> 混合检索 -> 重排序 -> 上下文组装 -> 答案生成，全链路可追溯 |
| **混合检索** | Hybrid Retrieval | 向量语义搜索 + BM25 关键词检索 + 融合排序（RRF），兼顾召回率与精确率 |
| **监管感知重排序** | Regulatory-aware Re-ranking | AI 判断查询合规相关性，对监管类文档施加固定加分并考虑时效性 |
| **流式输出** | Streaming Output | Server-Sent Events 实时推送检索上下文与生成 Token，前端逐帧展示 |
| **多模型支持** | Multi-model Support | 兼容 OpenAI API 协议，支持 SiliconFlow / 本地模型双轨部署 |
| **异步架构** | Async Architecture | FastAPI + SQLAlchemy async + ChromaDB 线程池，高并发下保持稳定响应 |
| **结构化日志** | Structured Logging | JSON 格式事件日志，涵盖启动、请求、错误、性能指标，便于生产监控 |
| **异常路径保障** | Resilience by Design | 即使模型/API 不可用，仍保证查询持久化并返回非空 query_id |

---

## 目录 | Table of Contents

- [数据准备 / Data Preparation](#数据准备--data-preparation)
- [算法原理 / Algorithm](#算法原理--algorithm)
- [模块文档 / Module Reference](#模块文档--module-reference)
- [快速开始 / Quick Start](#快速开始--quick-start)
- [输出说明 / Output](#输出说明--output)
- [安装依赖 / Installation](#安装依赖--installation)
- [项目结构 / Project Structure](#项目结构--project-structure)
- [引用 / Citation](#引用--citation)
- [许可证 / License](#许可证--license)

---


## 数据准备 | Data Preparation

在开始使用前，请准备好以下资源：

1. **保险文档**：将 PDF 格式的保险条款、监管文件、产品说明书等放入 `data/documents/pdfs/` 目录
2. **API 密钥**：注册 [SiliconFlow](https://siliconflow.cn) 或兼容 OpenAI API 的服务商，获取 API Key
3. **可选 - OCR 引擎**：如需解析扫描版 PDF，安装 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) 并配置中文语言包

> Before getting started, prepare insurance PDF documents in `data/documents/pdfs/`, obtain an LLM API key from SiliconFlow or any OpenAI-compatible provider, and optionally install Tesseract OCR for scanned document parsing.

文档摄取命令：

```bash
# 基本摄取（解析 -> 分块 -> 嵌入 -> 写入向量库）
python ingest.py

# 仅准备阶段（生成分块 JSON，不写向量库）
set PREPARE_ONLY=1
python ingest.py

# 重建向量库（清库后重建）
set REBUILD_VECTOR_DB=1
python ingest.py
```

| 参数 | Parameter | 默认值 | 说明 |
|------|-----------|--------|------|
| `PREPARE_ONLY` | Prepare Only | 0 | 仅生成 `chunks.jsonl`，不写入向量库 |
| `REBUILD_VECTOR_DB` | Rebuild Vector DB | 0 | 清空向量库后重新写入 |
| `DOC_BATCH_SIZE` | Doc Batch Size | 32 | 嵌入批处理大小 |
| `USE_LOCAL_EMBEDDINGS` | Use Local Embeddings | 0 | 使用本地嵌入模型（离线环境） |

---

## 算法原理 | Algorithm

### 检索增强生成（RAG）管线

```
用户问题
    |
    v
[Step 1] 查询改写 (Query Rewriter)
    |   - 基于 LLM 对口语化问题进行意图规范化
    |   - 集成保险本体库，修正术语表达
    v
[Step 2] 混合检索 (Hybrid Retrieval)
    |   - 向量检索：ChromaDB 语义相似度搜索
    |   - 关键词检索：BM25 稀疏检索（jieba 分词）
    |   - 融合：倒数排名融合 (RRF)
    v
[Step 2.5] 监管感知重排序 (Regulatory Re-ranking)
    |   - AI 判断查询是否为监管/合规相关
    |   - 对关联文档施加固定加分 + 时效性降序
    v
[Step 3] 上下文选择 (Context Assembly)
    |   - 基于相似度阈值与 chunk 数量上限筛选
    |   - 构建 LLM 提示上下文
    v
[Step 4] 答案生成 (Answer Generation)
    |   - LLM 基于检索上下文生成回答
    |   - 支持流式（SSE）与非流式两种模式
    v
[Step 5] 后处理与持久化 (Post-processing)
    |   - 记录耗时、置信度、来源片段
    |   - 查询历史持久化（异常路径亦保证）
    v
  输出结果
```

### 融合排序（Fusion Scoring）

采用加权线性排序，综合语义相似度与业务相关性：

- `final_score = W_orig * similarity + W_biz * business_score`
- 监管相关文档额外加分，已过期文档惩罚系数 `x0.3`
- 计算结果与时效性（6 个月内阶跃加分）共同决定最终排序

> The system employs a weighted linear fusion of semantic similarity and business relevance, with regulatory boost and expiry penalty, to determine the final ranking of retrieved chunks.

### 查询改写策略

当 `ENABLE_QUERY_REWRITING=True` 时，系统在检索前对用户问题进行轻量改写：
- 保留最近 10 轮会话历史（截断至 4000 字符）
- 基于保险本体库进行术语对齐
- 改写结果仅用于检索，不改变持久化的原始问题

---

## 模块文档 | Module Reference

### 核心 API 端点

| 端点 | Endpoint | 方法 | 说明 |
|------|----------|------|------|
| `/api/v1/queries/ask` | Ask Question | POST | 提交自然语言问题，返回检索增强答案 |
| `/api/v1/queries/ask/stream` | Stream Answer | POST | 流式接口，SSE 逐事件推送 |
| `/api/v1/queries/history` | Query History | GET | 获取查询历史（支持分页与计数） |
| `/api/v1/queries/history/{id}` | Query Detail | GET | 获取单条查询详情 |
| `/api/v1/queries/history/{id}/feedback` | Submit Feedback | POST | 提交答案反馈 |
| `/api/v1/queries/statistics` | Query Stats | GET | 查询统计 |
| `/api/v1/health/live` | Liveness | GET | 存活检查 |
| `/api/v1/health/ready` | Readiness | GET | 就绪检查 |
| `/api/v1/health/model` | Model Info | GET | 模型与嵌入信息 |

### 询问请求参数

| 参数 | Parameter | 类型 | 默认值 | 说明 |
|------|-----------|------|--------|------|
| `question` | Question | str | - | 用户自然语言问题（必填） |
| `query_type` | Query Type | str | general | `general` 或 `regulatory` |
| `max_chunks` | Max Chunks | int | 5 | 上下文最大片段数 |
| `top_k` | Top K | int | 8 | 语义检索候选数量 |
| `similarity_threshold` | Similarity Threshold | float | 0.35 | 相似度阈值（监管类建议 0.5-0.7） |
| `session_id` | Session ID | str | null | 多轮对话会话标识 |
| `return_sources` | Return Sources | bool | true | 是否返回检索来源详情 |
| `language` | Language | str | zh | 期望回答语言 |

### 核心服务模块

| 模块 | Module | 职责 |
|------|--------|------|
| `app.core.rag_workflow` | RAG Workflow | 编排查询改写、检索、重排、生成全流程 |
| `app.services.query_service` | Query Service | 端到端查询处理与异常路径持久化 |
| `app.services.llm_service` | LLM Service | 模型调用封装（OpenAI 兼容协议） |
| `app.services.vector_store` | Vector Store | 向量库封装与检索接口 |
| `app.services.embedding_service` | Embedding Service | 嵌入模型管理与并发调用 |
| `app.services.query_rewriter_service` | Query Rewriter | 基于 LLM 的查询改写 |
| `app.core.structured_logger` | Structured Logger | JSON 事件日志 |

---


## 快速开始 | Quick Start

### 环境要求

- Python 3.8+
- 8GB+ RAM（推荐）
- 10GB+ 可用磁盘空间

### 安装与启动

```bash
# 1. 克隆项目
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API 密钥

# 5. 摄取文档
python ingest.py

# 6. 启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 使用示例

```bash
# 提交问题
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"question": "这份保险的保障范围是什么？", "query_type": "general"}'

# 流式问答
curl.exe -X POST "http://127.0.0.1:8000/api/v1/queries/ask/stream" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"question": "比较重疾险与医疗险的保障差异", "max_chunks": 6}'

# 查看查询历史
curl -X GET "http://127.0.0.1:8000/api/v1/queries/history"

# 健康检查
curl -X GET "http://127.0.0.1:8000/api/v1/health/live"
```

### Python 调用

```python
import requests

BASE_URL = "http://127.0.0.1:8000"

# 提交查询
resp = requests.post(f"{BASE_URL}/api/v1/queries/ask", json={
    "question": "重疾险的理赔流程是什么？",
    "query_type": "general",
})
data = resp.json()
print(f"Answer: {data['answer']}")
print(f"Confidence: {data['confidence_score']}")
print(f"Chunks used: {data['chunks_used']}")
```

---

## 输出说明 | Output

### 响应格式

非流式查询返回 JSON 对象：

```json
{
  "query_id": 23,
  "question": "这份保险的保障范围是什么？",
  "answer": "本保险的保障范围包含住院医疗、重疾、意外伤害...",
  "query_type": "general",
  "response_time": 7.42,
  "chunks_used": 5,
  "retrieved_chunks": [
    {
      "doc_id": "policy-2024-A",
      "chunk_id": 118,
      "score": 0.83,
      "content_preview": "本保险的保障范围包含住院医疗、重疾、意外...",
      "metadata": {"effective_date": "2024-10-01"}
    }
  ],
  "confidence_score": 0.76,
  "metadata": {
    "rewritten_query": "该保单保障范围？",
    "rewriting_metadata": {"model": "Qwen/Qwen2.5-7B-Instruct"}
  }
}
```

### 流式事件

流式接口（SSE）按事件类型推送：

| 事件 | Event | 触发时机 | 内容 |
|------|-------|----------|------|
| `start` | Start | 连接建立 | query_id 与上下文信息 |
| `context` | Context | 检索完成 | retrieved_chunks 原始片段列表 |
| `token` | Token | 生成过程中 | 增量生成 token |
| `end` | End | 生成完成 | 完整 answer 与统计信息 |
| `error` | Error | 异常发生 | 错误描述与提示 |

### 控制台输出示例

```text
[INFO] InsurIntellect Agent 正在启动...
[INFO] 数据库初始化完成
[INFO] BM25 索引与映射已在启动阶段加载并缓存
[INFO] HTTP请求: POST /api/v1/queries/ask
[INFO] HTTP响应: 200
[INFO] 查询处理完成: 耗时 7.42s, 使用 5 个片段, 置信度 0.76
```


## 安装依赖 | Installation

使用 pip 一键安装所有依赖：

```bash
pip install -r requirements.txt
```

下表列出了项目所有的依赖包及其版本和用途：

> Install all dependencies with a single pip command. The table below lists every required package with its version and purpose.

| 依赖 | Package | 版本 | 用途 |
|------|---------|------|------|
| fastapi | ==0.104.1 | Web 框架 | Web framework |
| uvicorn[standard] | ==0.33.0 | ASGI 服务器 | ASGI server |
| starlette | >=0.27.0 | ASGI 框架 | ASGI framework |
| openai | ==1.109.1 | OpenAI API 客户端 | OpenAI API client |
| langchain | ==0.2.17 | LangChain 框架 | LangChain framework |
| langchain-openai | ==0.1.8 | LangChain-OpenAI 集成 | LangChain-OpenAI integration |
| langchain-chroma | ==0.1.2 | LangChain-ChromaDB 集成 | LangChain-ChromaDB integration |
| langchain-community | ==0.2.19 | LangChain 社区集成 | LangChain community integrations |
| langchain-text-splitters | ==0.2.4 | 文本分割器 | Text splitters |
| langchain-core | >=0.2.0 | LangChain 核心库 | LangChain core library |
| langchain-huggingface | ==1.0.1 | LangChain-HuggingFace 集成 | LangChain-HuggingFace integration |
| sentence-transformers | ==3.2.1 | 句子嵌入模型 | Sentence embedding models |
| accelerate | ==0.31.0 | GPU 加速 | GPU acceleration |
| transformers | ==4.45.1 | Transformer 模型 | Transformer models |
| torch | >=2.0.0 | 深度学习框架 | Deep learning framework |
| tiktoken | ==0.7.0 | Token 计数 | Token counting |
| onnxruntime | ==1.19.2 | ONNX 推理引擎 | ONNX inference engine |
| chromadb | ==0.5.23 | 向量数据库 | Vector database |
| pypdf | ==5.9.0 | PDF 解析 | PDF parsing |
| PyPDF2 | ==3.0.1 | PDF 解析 | PDF parsing |
| pdfplumber | ==0.11.5 | PDF 表格解析 | PDF table parsing |
| python-multipart | ==0.0.20 | 文件上传解析 | File upload parsing |
| pymupdf | ==1.24.10 | PDF 渲染与解析 | PDF rendering & parsing |
| pytesseract | ==0.3.10 | OCR 文字识别 | OCR text recognition |
| Pillow | ==10.3.0 | 图像处理 | Image processing |
| unstructured | ==0.18.18 | 非结构化文档解析 | Unstructured document parsing |
| unstructured-inference | ==0.7.34 | 文档解析推理 | Document parsing inference |
| pdfminer.six | ==20231228 | PDF 文本提取 | PDF text extraction |
| beautifulsoup4 | ==4.12.3 | HTML/XML 解析 | HTML/XML parsing |
| opencv-python-headless | ==4.10.0.84 | 计算机视觉 | Computer vision |
| pandas | ==2.1.3 | 数据分析 | Data analysis |
| numpy | ==1.24.4 | 数值计算 | Numerical computation |
| scikit-learn | ==1.3.2 | 机器学习 | Machine learning |
| datasets | ==2.19.0 | 数据集管理 | Dataset management |
| sqlalchemy | ==2.0.23 | 数据库 ORM | Database ORM |
| asyncpg | ==0.29.0 | PostgreSQL 异步驱动 | PostgreSQL async driver |
| aiosqlite | ==0.20.0 | SQLite 异步驱动 | SQLite async driver |
| python-dotenv | ==1.0.1 | 环境变量管理 | Environment variable management |
| pydantic | ==2.8.2 | 数据验证 | Data validation |
| pydantic-settings | ==2.8.1 | 设置管理 | Settings management |
| PyYAML | ==6.0.3 | YAML 配置解析 | YAML configuration parsing |
| loguru | ==0.7.3 | 日志记录 | Logging |
| coloredlogs | ==15.0.1 | 彩色日志 | Colored logging |
| psutil | ==5.9.8 | 系统监控 | System monitoring |
| requests | ==2.32.4 | HTTP 客户端 | HTTP client |
| httpx | ==0.28.1 | HTTP 客户端（异步） | HTTP client (async) |
| aiofiles | ==24.1.0 | 异步文件操作 | Async file I/O |
| click | ==8.1.8 | CLI 工具 | CLI toolkit |
| tqdm | ==4.67.1 | 进度条 | Progress bar |
| backoff | ==2.2.1 | 指数退避重试 | Exponential backoff retry |
| tenacity | ==8.5.0 | 重试机制 | Retry mechanism |
| pytest | ==7.4.3 | 测试框架 | Testing framework |
| pytest-asyncio | ==0.21.1 | 异步测试支持 | Async test support |
| rank_bm25 | ==0.2.2 | BM25 检索算法 | BM25 retrieval algorithm |
| jieba | ==0.42.1 | 中文分词 | Chinese tokenization |

---

## Docker 使用 | Docker Usage

本项目为 FastAPI Web 服务，完全适合 Docker 部署。

```bash
# 构建镜像
docker build -t insurintellect-agent .

# 验证导入
docker run --rm insurintellect-agent

# 启动服务
docker run -p 8000:8000 insurintellect-agent uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 项目结构 | Project Structure

项目目录结构如下：

> The project source tree is organized as follows:

```
InsurIntellect_Agent/
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── services/
│   ├── prompts.py
│   └── __init__.py
├── scripts/
├── tools/
├── static/
├── ingest.py
├── requirements.txt
├── .env.example
├── setup.py
├── LICENSE
└── README.md
```

---

## 引用 | Citation

如果您在学术工作中使用了本项目，请按以下格式引用：

> If you use this project in academic work, please cite it as:

```bibtex
@software{InsurIntellect_Agent,
  author       = {Phoenix0531-sudo},
  title        = {{InsurIntellect Agent}: Intelligent Insurance Document Q\&A System},
  year         = {2026},
  url          = {https://github.com/Phoenix0531-sudo/InsurIntellect-Agent},
  version      = {1.0.0},
  license      = {MIT},
}
```

---

## 许可证 | License

本项目采用 MIT 许可证。详情请参阅 [LICENSE](LICENSE) 文件。

> This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

<div align="center">**Made for the insurance intelligence community**</div>
