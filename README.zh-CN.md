# InsurIntellect Agent

**保险文档智能问答：PDF 入库 → 切块/向量 → Chroma + BM25 混合检索 → FastAPI 作答。**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

领域 PDF 的演示 / 研究助手。**非持牌保险建议**，也不是保险公司生产系统。

## 预览

![InsurIntellect Agent](docs/screenshots/preview.png)

## 两阶段

1. **`ingest.py`**：读 PDF、切块、Chroma 向量库、**BM25Plus + jieba** 中文词法检索  
2. **`app/`**：FastAPI；`query_service` 检索 + LLM（流式路径使用已定义的 `llm_core` / `llm_light`）

## 安装运行

```bash
pip install -r requirements.txt
python ingest.py --help
uvicorn app.main:app --reload
pytest tests/
```

密钥走环境变量，禁止入库。

## 范围

本地 RAG、混合检索、API 问答；不做持牌建议与多租户 SaaS。

## 许可证

MIT。详见 [LICENSE](LICENSE)。
