# InsurIntellect Agent

**基于 LLM + 向量检索的保险文档问答（FastAPI）。**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

入库、检索、作答。仅演示 / 研究助手。

## 预览

![InsurIntellect Agent](docs/screenshots/preview.png)

## 功能

- PDF / 文本入库向量库
- 检索增强的 LLM 作答
- app/ 下 FastAPI 服务
- 入库脚本 + monitoring / reports
- 严格 CI（关键 ruff + pytest）

## 快速开始

### 安装

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
pip install -r requirements.txt
```

### 使用

```bash
python ingest.py --help
uvicorn app.main:app --reload
pytest tests/
```

## 项目结构

```
app/  ingest.py
data/ logs/ reports/ monitoring/
tests/
```

## 说明

非持牌保险建议，也不是保险公司生产系统。

## 许可证

MIT。在注明出处的前提下可商业使用（以 LICENSE 为准）。详见 [LICENSE](LICENSE)。
