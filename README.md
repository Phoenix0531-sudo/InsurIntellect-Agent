# InsurIntellect Agent

基于大语言模型与向量数据库的保险文档问答系统，提供智能的保险文档分析和问答服务。

## 🚀 功能特性

- **向量搜索**: 基于 ChromaDB/Pinecone 的语义检索
- **智能问答**: 基于兼容 OpenAI API 的模型（默认 SiliconFlow）
- **查询历史**: 完整的查询记录和反馈系统
- **系统监控**: 实时性能监控和健康检查
- **管理后台**: 完善的系统管理和统计分析

## 📋 系统要求

- Python 3.8+
- 8GB+ RAM (推荐)
- 10GB+ 可用磁盘空间

## 🛠️ 安装部署

### 1. 克隆项目

```bash
git clone <repository-url>
cd InsurIntellect_Agent
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 环境配置

复制环境变量模板并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的环境变量（示例值可根据需调整）：

```env
# OpenAI/SiliconFlow API配置（默认走 SiliconFlow 兼容 OpenAI API）
OPENAI_API_KEY=your_siliconflow_api_key
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Qwen/Qwen2.5-7B-Instruct
OPENAI_EMBEDDING_MODEL=BAAI/bge-m3

# 向量数据库配置 (选择一种)
VECTOR_DB_TYPE=chroma  # 或 pinecone
CHROMA_PERSIST_DIRECTORY=./data/vector_db/chroma

# 数据库配置（默认与代码一致）
DATABASE_URL=sqlite:///./data/database/app.db

# 应用配置
HOST=127.0.0.1
PORT=8000
RELOAD=true
SECRET_KEY=your_secret_key_here
DEBUG=true
LOG_LEVEL=INFO
```

### 5. 初始化数据库

应用启动时会自动初始化数据库。如需手动初始化：

```bash
python -c "import asyncio; from app.core.database import init_db; asyncio.run(init_db())"
```

### 6. 启动应用

推荐使用 Uvicorn 启动（Windows）：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

应用默认在 `http://127.0.0.1:8000` 启动。根路径 `/` 会返回前端页面 `static/index.html`。

## 📚 API 文档

启动应用后，访问以下地址查看 API 文档与服务信息：

- 服务信息: `http://127.0.0.1:8000/api`
- Swagger UI: `http://127.0.0.1:8000/docs`（仅调试模式）
- ReDoc: `http://127.0.0.1:8000/redoc`（仅调试模式）

## 🔧 主要 API 端点

所有业务路由均挂载在 `/api/v1` 下。

### 查询问答（/api/v1/queries）

- `POST /api/v1/queries/ask` - 提交问题查询
- `GET /api/v1/queries/history/{id}` - 获取查询详情
- `POST /api/v1/queries/history/{id}/feedback` - 提交反馈
- `GET /api/v1/queries/statistics` - 查询统计
- `POST /api/v1/queries/batch` - 批量查询

### 系统与健康（/api/v1/health, /api/v1/admin）

- `GET /api/v1/health/live` - 存活检查
- `GET /api/v1/health/ready` - 就绪检查
- `GET /api/v1/health/model` - 模型信息（包括嵌入模型）
- `GET /api/v1/admin/system/info` - 系统信息
- `GET /api/v1/admin/system/backups` - 备份列表
- `DELETE /api/v1/admin/system/backups/{name}` - 删除备份

## 📁 项目结构

```
InsurIntellect_Agent/
├── app/                          # 应用主目录
│   ├── main.py                   # 应用入口（通过 uvicorn 运行）
│   ├── api/                      # API 路由
│   │   ├── routes.py             # 主路由聚合（挂载 /api/v1）
│   │   └── endpoints/            # API 端点
│   │       ├── health.py         # 健康检查
│   │       ├── queries.py        # 查询处理
│   │       └── admin.py          # 管理功能
│   ├── core/                     # 核心功能
│   │   ├── config.py             # 配置管理（读取 .env）
│   │   ├── database.py           # 数据库配置与初始化
│   │   ├── chromadb_manager.py   # ChromaDB 单例
│   │   ├── logging.py            # 日志配置
│   │   └── rag_workflow.py       # RAG 工作流
│   ├── models/                   # 数据模型
│   │   ├── database_models.py    # 数据库模型
│   │   └── schemas.py            # API 模式定义
│   ├── services/                 # 业务逻辑
│   │   ├── vector_store.py       # 向量存储服务
│   │   ├── llm_service.py        # LLM 服务
│   │   └── query_service.py      # 查询服务
│   └── prompts.py                # 提示词模板
├── data/                         # 数据存储
│   ├── vector_db/                # 向量数据库
│   ├── processed/                # 处理后数据
│   └── database/                 # SQLite 数据库
├── docs/                         # 文档目录
│   ├── tesseract_setup.md        # OCR 配置指南
│   ├── siliconflow_setup.md      # SiliconFlow 配置
│   └── pipeline_modes.md         # 管道模式说明
├── scripts/                      # 工具脚本
│   ├── clear_vector_db.py        # 清理向量数据库
│   ├── embed_chunks.py           # 嵌入向量生成
│   └── validate_retrieval.py     # 检索验证
├── static/                       # 前端静态资源（根路径返回 index.html）
│   ├── index.html                # 主页面
│   ├── css/                      # 样式文件
│   └── js/                       # JavaScript 文件
├── test/                         # 测试文件
│   ├── test_api.py               # API 端点测试
│   ├── test_rag_workflow.py      # RAG 工作流测试
│   ├── test_web_interface.py     # Web 界面测试
│   └── check_db.py               # 数据库检查
├── ingest.py                     # 文档摄取脚本
├── requirements.txt              # Python 依赖
├── .env.example                  # 环境变量模板
└── README.md                     # 项目文档

## 🔍 使用示例

### 1. 智能问答

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这份保险的保障范围是什么？",
    "query_type": "general",
    "max_chunks": 5
  }'
```

### 2. 获取查询详情

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/queries/history/1"
```

### 3. 健康检查与模型信息

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/health/model"
curl -X GET "http://127.0.0.1:8000/api/v1/health/live"
curl -X GET "http://127.0.0.1:8000/api/v1/health/ready"
```

## ⚙️ 配置说明

### 向量数据库配置

支持两种向量数据库：

**ChromaDB (本地)**:
```env
VECTOR_DB_TYPE=chroma
CHROMA_PERSIST_DIRECTORY=./data/vector_db/chroma
```

**Pinecone (云端)**:
```env
VECTOR_DB_TYPE=pinecone
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment
PINECONE_INDEX_NAME=insurintellect-index
```

### LLM/嵌入模型配置（兼容 OpenAI API）

```env
# 走 SiliconFlow 兼容 OpenAI API
OPENAI_API_KEY=your_siliconflow_api_key
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Qwen/Qwen2.5-7B-Instruct
OPENAI_EMBEDDING_MODEL=BAAI/bge-m3  # 或 BAAI/bge-large-zh-v1.5
OPENAI_MAX_TOKENS=1000
OPENAI_TEMPERATURE=0.7
```

### OCR 安装与配置（Windows）

- 项目在解析扫描版 PDF 时会回退到 OCR（Tesseract）。如遇到 `tesseract is not installed or it's not in your PATH`，请完成安装与配置。
- 安装与配置指南请参见：`docs/tesseract_setup.md`
- 快速配置要点：
  - 安装路径建议保留默认 `C:\\Program Files\\Tesseract-OCR`
  - 在 `.env` 设置 `TESSERACT_CMD` 和 `OCR_LANG`（例如 `chi_sim+eng`）
  - 或在 `app/core/ingestion_config.yml` 设置 `general.ocr.tesseract_cmd`

## 🧪 测试

项目包含完整的测试套件，位于 `test/` 目录：

### 运行测试

```bash
# 运行所有API端点测试
python test/test_api.py

# 运行RAG工作流测试
python test/test_rag_workflow.py

# 运行Web界面测试
python test/test_web_interface.py

# 检查数据库连接
python test/check_db.py
```

### 测试覆盖

- **API端点测试**: 验证所有REST API端点功能
- **RAG工作流测试**: 测试检索增强生成流程
- **Web界面测试**: 验证前端交互和API集成
- **数据库测试**: 检查数据库连接和向量数据库状态

### 测试结果示例

```
✅ API端点测试: 7/7 通过
✅ RAG工作流测试: 所有测试通过
✅ Web界面测试: 5/5 通过 (100%成功率)
✅ 数据库检查: 连接正常
```

## 🚀 部署建议

### Docker 部署

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 生产环境配置

1. 使用PostgreSQL替代SQLite
2. 配置反向代理(Nginx)
3. 启用HTTPS
4. 配置日志轮转
5. 设置监控告警

## 🔧 开发指南

### 添加新的 API 端点

1. 在 `app/api/endpoints/` 创建新的端点文件
2. 在 `app/api/routes.py` 中注册路由
3. 更新相关的Pydantic模型

### 添加新的服务

1. 在 `app/services/` 创建服务文件
2. 实现业务逻辑
3. 在 `__init__.py` 中导出服务

### 数据库迁移

```bash
# 创建新的迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head
```

## 🐛 故障排除

### 常见问题

1. **OpenAI API错误**: 检查API密钥和网络连接
2. **向量数据库连接失败**: 验证配置和服务状态
3. **内存不足**: 调整批处理大小和并发数

### 日志查看

```bash
# 查看应用日志
tail -f logs/app.log

# 查看错误日志
tail -f logs/error.log
```

## 📈 性能优化

1. **文档分块优化**: 调整chunk_size和overlap参数
2. **向量搜索优化**: 调整相似度阈值和返回数量
3. **缓存策略**: 启用查询结果缓存
4. **并发处理**: 配置合适的worker数量

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 支持

如有问题或建议，请：

1. 查看文档和FAQ
2. 搜索已有的Issues
3. 创建新的Issue
4. 联系开发团队

---

**InsurIntellect Agent** - 让保险文档问答更智能！

## 项目概述

InsurIntellect Agent 是一个智能保险文档问答系统，利用大语言模型和向量数据库技术，为用户提供准确、高效的保险文档查询和问答服务。

## 功能特性

- 📄 PDF文档自动解析和预处理
- 🔍 基于向量相似度的智能检索
- 🤖 大语言模型驱动的问答生成
- 🚀 RESTful API接口
- 📊 查询历史和性能监控
- 🔧 灵活的配置管理

## 技术栈

- **后端框架**: FastAPI
- **向量数据库**: ChromaDB / Pinecone
- **嵌入模型**: OpenAI Embeddings / Sentence Transformers
- **大语言模型**: OpenAI GPT / 其他兼容模型
- **数据库**: SQLite / PostgreSQL
- **部署**: Docker, Uvicorn

## 快速开始

### 环境要求

- Python 3.8+
- pip 或 conda

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的API密钥和配置
```

### 运行应用

```bash
python main.py
```

## 项目结构

详见项目目录结构说明。

## 贡献指南

欢迎提交Issue和Pull Request来改进项目。

## 许可证

MIT License
