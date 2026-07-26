# InsurIntellect Agent

**保险条款 RAG：本地 PDF 语料 → 混合检索 → 带引用回答。**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

本地演示产品：对「已入库保险条款」做有依据的问答。  
**不构成受监管保险建议（Not regulated insurance advice）。** 不是多租户 SaaS，不是持牌顾问，不是 Agent 编排平台。

## 预览

![InsurIntellect 条款 RAG 界面](docs/screenshots/preview.png)

左侧：已索引文档 + 示例问题；右侧：结构化答案与引用卡（文档名 / 页码 / 摘录）。

## 架构

```
samples/*.pdf  →  data/documents/pdfs
        ↓
 simple_ingest.py  →  Chroma + BM25/jieba + corpus_manifest
        ↓
 POST /api/v1/queries/ask
   hybrid 检索 → 低分/离题/购保建议拒答
   → OpenAI 兼容网关生成「结论 / 条款依据 / 边界」
        ↓
 static/ 浅色双栏 UI
```

默认 `SIMPLE_RAG_MODE=true`：retrieve → generate。  
查询重写、SQL 路由、KG、监管多 Agent 默认关闭。

## 快速开始（uv）

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent

uv venv .venv --python 3.11
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
uv pip install pytest ruff httpx

cp .env.example .env
# 填写 OPENAI_BASE_URL / OPENAI_API_KEY（OpenAI 兼容网关，如本机 new-api）
# 默认嵌入：hf:BAAI/bge-small-zh-v1.5（本机 HF 缓存；首次下载可能需要代理）
# 离线回退：OPENAI_EMBEDDING_MODEL=local:hash（切换后需重新 ingest）

uv run python scripts/generate_sample_corpus.py --copy-to-data
uv run python scripts/simple_ingest.py --reset

export HOST=127.0.0.1 PORT=8766
uv run uvicorn app.main:app --host 127.0.0.1 --port 8766
# 浏览器打开 http://127.0.0.1:8766/
```

无 API Key 时：接口仍返回检索片段，并明确提示 **LLM 不可用**，不会静默编造。

## 固定演示三问

| ID | 问题 | 期望 |
|----|------|------|
| Q1 | 等待期是多久？ | 命中样例条款并带引用 |
| Q2 | 责任免除包括哪些情形？ | 多点列举 + 引用 |
| Q3 | 这份保单保证我一定能获赔吗？ | 强边界 / 拒给购买或保证承诺 |

## 范围

**做**：本地条款语料、混合检索、引用回答、拒答与降级、证据型 UI。  
**不做**：持牌建议、理赔承诺、完整 PDF 阅读器、多租户登录；KG/SQL 产品化（代码可保留为 advanced）。


<!-- polish-demo-notes -->
## 演示启动（强制 embedding）

Shell 环境可能污染 `.env`。启动时务必强制与入库相同的向量模型：

```bash
export OPENAI_EMBEDDING_MODEL=hf:BAAI/bge-small-zh-v1.5
export SIMILARITY_THRESHOLD=0.32
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
bash scripts/run_demo.sh
# Windows: scripts\run_demo.bat
```

更换 embedding 后必须重新入库：

```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/simple_ingest.py --reset
```

固定回归（服务需已启动）：

```bash
.venv/Scripts/python.exe scripts/demo_smoke.py
```

Docker 可选（`Dockerfile` 默认暴露 8000）。作品集本地演示优先 `uv` + **8766**，不要绑死 Docker。

## 许可

MIT，见 [LICENSE](LICENSE)。
