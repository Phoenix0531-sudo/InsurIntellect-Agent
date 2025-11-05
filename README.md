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
# OpenAI/SiliconFlow API配置（二选一即可，均兼容）
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_API_KEY=your_siliconflow_api_key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
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
ENABLE_STRUCTURED_LOGGING=true
STRUCTURED_LOG_FILE=logs/structured.log
ENABLE_AUTO_RESTART=false
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
│   │   ├── app_logging.py        # 日志配置（标准 logging）
│   │   ├── structured_logger.py  # 结构化日志（JSON事件）
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
│   ├── validate_retrieval.py     # 检索验证（输出JSON文件路径）
│   ├── search_pdf_terms.py       # PDF术语提取（标准输出JSON）
│   └── cleanup_tests.py          # 测试临时文件清理
├── static/                       # 前端静态资源（根路径返回 index.html）
│   ├── index.html                # 主页面
│   ├── css/                      # 样式文件
│   └── js/                       # JavaScript 文件
├── tools/                         # 测试文件和维护工具
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

## ⚖️ 监管关联排序（Regulatory-aware Ranking）

- 目标：当用户问题与保险监管/法规/合规高度相关时，优先展示与该监管问题高度关联的产品文档，以便更好地说明监管影响。
- 启用方式：配置 `settings.ENABLE_REGULATORY_RERANK = True`（默认已启用）。
- 固定加分：对被判定“监管相关且与该查询高度关联”的产品文档，应用固定加分 `settings.REGULATORY_FIXED_BOOST`（默认 `100.0`）。
- 识别策略：
  - 查询识别（推荐：AI）——轻量级AI判定“该问题是否与保险监管、法规或合规性高度相关？只回答是/否”。失败时回退到关键词列表 `settings.REGULATORY_KEYWORDS`（如“监管、合规、评级、ESG、银保监、保监”）。
  - 文档关联（推荐：AI）——向AI提供文档片段与元数据，请其判定“该产品文档是否与这个监管相关查询高度关联？只回答是/否”。失败时使用“若文档类型不含‘监管’，则视为弱关联”的回退策略。
- 排序规则：
  - 首先按“是否监管关联的产品文档”优先级重排（固定加分实现强置顶效果）。
  - 然后按“文档有效日期”降序排序，兼顾时效性。
- 设计取舍：
  - 采用“AI判断 + 固定加分”（选项 1B + 2B + 3A），在演示场景下兼顾效果显著与实现稳定。
  - 后续可以切换为“动态加分”（3B），将加分与关联程度成比例，获得更精细的排序控制。

### 相关配置字段

- `ENABLE_REGULATORY_RERANK`：是否启用监管感知重排序（默认：True）。
- `REGULATORY_FIXED_BOOST`：固定加分数值（默认：100.0）。
- `REGULATORY_KEYWORDS`：监管关键词回退列表（默认：`["监管", "合规", "评级", "ESG", "银保监", "保监"]`）。

### 工作流中的位置

- 在检索阶段（RAG 第 2 步）后执行“2.5 监管感知重排序”。
- 在评审选择（第 3 步）后，最终上下文组装前再次按“监管关联优先 + 时效性”排序。

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

项目在解析扫描版 PDF 时会回退到 OCR（Tesseract）。如遇到 `tesseract is not installed or it's not in your PATH`，请完成安装与配置。

#### 安装 Tesseract

1. **下载安装包**：
   - 访问：https://github.com/UB-Mannheim/tesseract/wiki
   - 下载 `tesseract-ocr-w64-setup-<version>.exe`（64位）
   - 安装时保留默认路径：`C:\Program Files\Tesseract-OCR`
   - 勾选中文语言包（`chi_sim` 简体中文）和英文（`eng`）

2. **配置项目**：
   ```env
   # 在 .env 文件中设置
   TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
   OCR_LANG=chi_sim+eng
   ```

3. **自动探测**：项目支持自动探测常见安装路径，无需手动配置

#### 验证安装
```powershell
tesseract --version
```

### SiliconFlow API 配置

#### 获取API密钥
1. 访问 [硅基流动官网](https://siliconflow.cn)
2. 注册账号并获取API密钥

#### 支持的模型
- `Qwen/Qwen2.5-7B-Instruct` - 通义千问2.5-7B指令模型（推荐）
- `Qwen/Qwen2.5-14B-Instruct` - 通义千问2.5-14B指令模型
- `deepseek-ai/DeepSeek-V2.5` - DeepSeek V2.5模型

#### API兼容性
硅基流动API与OpenAI API完全兼容，只需修改：
- `base_url` 为 `https://api.siliconflow.cn/v1`
- `api_key` 为您的硅基流动API密钥
- `model` 为硅基流动支持的模型名称

## 🧪 测试

项目包含完整的测试套件，位于 `tools/` 目录：

### 运行测试

```bash
# 运行所有API端点测试
python tools/test_api.py

# 运行RAG工作流测试
python tools/test_rag_workflow.py

# 运行Web界面测试
python tools/test_web_interface.py

# 检查数据库连接
python tools/check_db.py
```

### 测试覆盖

- **API端点测试**: 验证所有REST API端点功能
- **RAG工作流测试**: 测试检索增强生成流程
- **Web界面测试**: 验证前端交互和API集成
- **数据库测试**: 检查数据库连接和向量数据库状态

### 系统测试状态

| 测试类别 | 通过率 | 状态 | 性能指标 |
|---------|--------|------|----------|
| 数据库连接 | 100% | ✅ 通过 | ChromaDB正常工作 |
| 文档检索 | 100% | ✅ 通过 | 向量搜索响应时间: ~0.02秒 |
| RAG工作流 | 100% | ✅ 通过 | 完整查询处理: ~7.5秒 |
| Web界面 | 100% | ✅ 通过 | 前端交互正常 |
| API端点 | 86% | ✅ 通过 | 核心功能完全可用 |

**系统状态**: ✅ **生产就绪** - 核心功能完全可用，性能表现良好

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

### 系统监控和维护

#### 端口管理
- 系统支持自动端口检测和分配
- 默认端口8000，冲突时自动切换到8001等可用端口
- 使用 `app/core/port_manager.py` 进行端口管理

#### 健康检查
```bash
# 检查系统健康状态
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/health/model
```

#### 性能优化建议
1. **查询优化**: 调整chunk_size和overlap参数优化文档分块
2. **向量搜索**: 调整相似度阈值和返回数量
3. **缓存策略**: 启用查询结果缓存提升响应速度
4. **并发处理**: 配置合适的worker数量

#### 故障排除
- **端口冲突**: 系统会自动检测并切换到可用端口
- **向量数据库**: 使用 `tools/` 目录下的检查和重置工具
- **日志查看**: 检查应用日志定位问题
- **进程管理**: 使用系统工具清理僵尸进程

#### 向量数据库管理

**清空向量库**：
```powershell
# 一键清空本地 Chroma 向量库
python scripts/clear_vector_db.py

# 重建向量库
python ingest.py

# 或临时清库重建
$env:REBUILD_VECTOR_DB = "1"; python ingest.py
```

**数据管线模式**：

1. **Prepare-Only（仅准备阶段）**：
   ```powershell
   $env:PREPARE_ONLY = "1"
   python ingest.py
   ```
   生成 `data/processed/chunks.jsonl`，包含分割后的文本块和元数据

2. **Embed-Only（仅嵌入与写库）**：
   ```powershell
   # 可选：重建矢量库
   $env:REBUILD_VECTOR_DB = "1"
   $env:DOC_BATCH_SIZE = "32"
   python scripts/embed_chunks.py
   ```

**嵌入模式选择**：
- **远端嵌入**：默认启用，使用 SiliconFlow API
- **本地嵌入**：设置 `USE_LOCAL_EMBEDDINGS=1` 使用本地模型

### 更多工具
- `tools/check_chromadb_metadata.py`：检查 ChromaDB 集合的元数据与配置
- `tools/check_embedding_dimensions.py`：验证嵌入模型维度与集合维度匹配
- `tools/reset_chromadb.py` / `tools/force_reset_chromadb.py`：重置或强制重置向量库

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

### 日志配置

- 标准日志：使用 `app.core.app_logging.setup_logging()` 初始化，遵循 `LOG_LEVEL`，支持同时输出到控制台与文件。
- 结构化日志：`app.core.structured_logger.StructuredLogger` 以 JSON 事件格式记录关键操作（启动、请求、错误、性能等）。
- 环境变量：
  - `LOG_LEVEL`（如 `INFO`/`DEBUG`）
  - `ENABLE_STRUCTURED_LOGGING=true|false`
  - `STRUCTURED_LOG_FILE=logs/structured.log`
- CLI 脚本：已统一使用日志输出，同时保留必要的标准输出：
  - `scripts/search_pdf_terms.py` 以标准输出打印 JSON 结果（便于管道处理）。
  - `scripts/validate_retrieval.py` 打印生成的 JSON 文件路径，并记录详细日志。
  - 两个脚本均支持 `--quiet`（等同于 `--log-only`）参数；启用后仅输出日志，不打印标准输出，适合在严格日志管道或后台任务中使用。

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
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

提示：若端口冲突，系统会自动回退到可用端口（如 8001），由 `app/core/port_manager.py` 管理。

## 项目结构

详见项目目录结构说明。

## 贡献指南

欢迎提交Issue和Pull Request来改进项目。

## 许可证

MIT License

## 维护与测试变更记录（2025-11-05）

- 清理操作：
  - 删除历史测试报告（`reports/test_report_*`、`reports/*.junit.xml`）与根目录 `test_cleanup_report.md`。
  - 仅保留最新报告：`reports/test_report_20251105_214024.md`。
- 修复脚本：
  - 将 `scripts/cleanup_tests.py` 中对 `setup_logging` 的调用由 `level=` 更正为 `log_level=`，修复意外参数错误（TypeError）。
- 测试执行：
  - 运行 `tools/test_api.py`、`tools/test_rag_workflow.py`、`tools/test_web_interface.py`，基础地址设为 `http://localhost:8001`。
- 测试结果摘要：
  - API 与 Web 测试均出现 `HTTPConnectionPool(host='localhost', port=8001)` 连接失败，表现为端口不可达或服务未就绪。
  - RAG 工作流测试未提供必要参数（`chunks_file`、`query`），触发 `argparse` 用法错误并退出。
- 当前项目状态：
  - 测试报告与临时测试文件已完成清理与归档，仅保留最新测试报告。
  - 建议按 README 的“启动应用”章节使用 `uvicorn` 启动，并在运行测试前通过 `GET /api/v1/health/live` 与 `GET /api/v1/health/ready` 验证服务就绪。
  - 如需稳定测试，可在 `tools/test_api.py` 与 `tools/test_web_interface.py` 增加就绪轮询与重试逻辑；为 `tools/test_rag_workflow.py`提供示例参数或默认值以避免因参数缺失失败。
- 复现步骤（示例）：
  - 启动服务：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload`
  - 运行测试：
    - `python tools/test_api.py`
    - `python tools/test_web_interface.py`
    - `python tools/test_rag_workflow.py data/processed/chunks.jsonl "监管相关条款有哪些？"`
