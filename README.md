# InsurIntellect Agent

基于大语言模型的保险文档问答系统，提供智能的保险文档分析和问答服务。

## 🚀 功能特性

- **文档处理**: 支持PDF文档上传、解析和分块处理
- **向量搜索**: 基于ChromaDB/Pinecone的语义搜索
- **智能问答**: 集成OpenAI GPT模型的上下文感知问答
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

编辑 `.env` 文件，配置必要的环境变量：

```env
# OpenAI API配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002

# 向量数据库配置 (选择一种)
VECTOR_DB_TYPE=chroma  # 或 pinecone
CHROMA_PERSIST_DIRECTORY=./data/vector_db/chroma

# 数据库配置
DATABASE_URL=sqlite:///./data/database/insurintellect.db

# 应用配置
SECRET_KEY=your_secret_key_here
DEBUG=false
LOG_LEVEL=INFO
```

### 5. 初始化数据库

```bash
python -c "from app.core.database import init_db; init_db()"
```

### 6. 启动应用

```bash
python main.py
```

应用将在 `http://localhost:8000` 启动。

## 📚 API 文档

启动应用后，访问以下地址查看API文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 🔧 主要API端点

### 文档管理

- `POST /api/documents/upload` - 上传PDF文档
- `GET /api/documents/` - 获取文档列表
- `GET /api/documents/{id}` - 获取文档详情
- `DELETE /api/documents/{id}` - 删除文档

### 查询问答

- `POST /api/queries/ask` - 提交问题查询
- `GET /api/queries/history` - 获取查询历史
- `POST /api/queries/history/{id}/feedback` - 提交反馈

### 系统监控

- `GET /api/health` - 健康检查
- `GET /api/health/stats` - 系统统计
- `GET /api/admin/system/info` - 系统信息

## 📁 项目结构

```
InsurIntellect_Agent/
├── app/                          # 应用主目录
│   ├── __init__.py
│   ├── api/                      # API路由
│   │   ├── __init__.py
│   │   ├── routes.py            # 主路由
│   │   └── endpoints/           # API端点
│   │       ├── __init__.py
│   │       ├── health.py        # 健康检查
│   │       ├── documents.py     # 文档管理
│   │       ├── queries.py       # 查询处理
│   │       └── admin.py         # 管理功能
│   ├── core/                    # 核心功能
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库配置
│   │   └── logging.py          # 日志配置
│   ├── models/                  # 数据模型
│   │   ├── __init__.py
│   │   ├── database_models.py  # SQLAlchemy模型
│   │   └── schemas.py          # Pydantic模型
│   └── services/               # 业务逻辑
│       ├── __init__.py
│       ├── document_service.py # 文档处理服务
│       ├── vector_store.py     # 向量存储服务
│       ├── llm_service.py      # LLM服务
│       └── query_service.py    # 查询服务
├── data/                       # 数据存储
│   ├── documents/              # 文档存储
│   ├── vector_db/              # 向量数据库
│   ├── processed/              # 处理后数据
│   └── database/               # SQLite数据库
├── logs/                       # 日志文件
├── main.py                     # 应用入口
├── requirements.txt            # Python依赖
├── .env.example               # 环境变量模板
├── .gitignore                 # Git忽略文件
└── README.md                  # 项目文档
```

## 🔍 使用示例

### 1. 上传文档

```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@insurance_policy.pdf"
```

### 2. 查询问答

```bash
curl -X POST "http://localhost:8000/api/queries/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这份保险的保障范围是什么？",
    "query_type": "general",
    "max_chunks": 5
  }'
```

### 3. 获取查询历史

```bash
curl -X GET "http://localhost:8000/api/queries/history?limit=10"
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

### LLM模型配置

```env
# OpenAI配置
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-3.5-turbo  # 或 gpt-4
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002
OPENAI_MAX_TOKENS=2000
OPENAI_TEMPERATURE=0.1
```

## 🚀 部署建议

### Docker部署

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "main.py"]
```

### 生产环境配置

1. 使用PostgreSQL替代SQLite
2. 配置反向代理(Nginx)
3. 启用HTTPS
4. 配置日志轮转
5. 设置监控告警

## 🔧 开发指南

### 添加新的API端点

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
3. **文档处理失败**: 检查PDF文件格式和大小
4. **内存不足**: 调整批处理大小和并发数

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
- **文档处理**: PyPDF2, pdfplumber
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