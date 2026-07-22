# InsurIntellect Agent

**保险文档智能问答：LLM + 向量检索（FastAPI）**

[English](README.md) | [中文](README.zh-CN.md)

![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

面向**保险**材料的文档问答栈：将 PDF / 文本入库向量库，用 LLM + 检索作答，`app/` 下 FastAPI 服务。

> 演示 / 研究助手——非受监管保险建议。

## 为什么做这个

保单 PDF 又长又术语密集。RAG Agent 是「LLM + 领域文档」的作品集切片，不宣称承保系统。

## 功能

- `ingest.py` 入库入口  
- `app/` FastAPI（API / services / prompts）  
- 可选依赖 `requirements-optional.txt`  
- monitoring / reports 运行产物  

## 安装

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
pip install -r requirements.txt
```

## 使用

```bash
python ingest.py --help
uvicorn app.main:app --reload
```

## 目录结构

```
app/
ingest.py
data/ logs/ reports/
tests/
```

## 许可证

MIT。可在署名前提下商用。见 [LICENSE](LICENSE)。
