# InsurIntellect Agent

**保险文档智能问答：LLM + 向量检索**

[English](README.md) | [中文](README.zh-CN.md)

![CI](https://github.com/Phoenix0531-sudo/InsurIntellect-Agent/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

保险文档智能问答：LLM + 向量检索。

> 作者：[Phoenix0531-sudo](https://github.com/Phoenix0531-sudo) · 欢迎学习、二次开发与**商业使用**，请保留本仓库署名与许可证声明。

## 技术栈

Python · LLM · RAG

## 功能特性

- 文档摄取与向量库
- 保险场景问答
- 监控与报告脚本

## 快速开始

```bash
git clone https://github.com/Phoenix0531-sudo/InsurIntellect-Agent.git
cd InsurIntellect-Agent
```

```bash
pip install -r requirements.txt
python ingest.py
# 启动 app 服务见 app/
```

更完整的英文说明见 [README.md](README.md)。

## 仓库结构（摘要）

```
InsurIntellect-Agent/
├─ .github/
├─ app/
├─ data/
├─ docs/
├─ logs/
├─ monitoring/
├─ reports/
├─ scripts/
├─ static/
├─ tools/
├─ CHANGELOG.md
├─ Dockerfile
├─ ingest.py
├─ LICENSE
├─ README.md
├─ README.zh-CN.md
├─ requirements-optional.txt
├─ requirements.txt
```

## 测试

```bash
pip install pytest
pytest -q
```

仓库内 `tests/` 至少包含 smoke 测试；有完整测试套件时以 CI 为准。

## CI

GitHub Actions（`push` / `pull_request`）会：

- 安装依赖（requirements / pyproject）
- 运行 `pytest`（**硬失败**）
- 尽力做语法/结构检查

## 许可证

[MIT](LICENSE) — 可自由使用、修改、分发与**商用**，需保留版权与许可声明（提及本仓库 / 作者即可）。

## 关于

维护者：[Phoenix0531-sudo](https://github.com/Phoenix0531-sudo)
