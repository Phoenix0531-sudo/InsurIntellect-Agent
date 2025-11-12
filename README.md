# InsurIntellect Agent

基于大语言模型与向量数据库的保险文档问答系统，提供智能的保险文档分析和问答服务。

## 目录
- 项目简介与特性
- 系统要求与安装部署
- 环境配置与变量详解
- 启动与运行（本地与Docker）
- API 文档与端点详解
- 响应模型与异常路径保证
- 项目结构与关键模块
- RAG 工作流与监管关联重排序
- 使用示例与测试验证
- 性能优化与监控日志
- 故障排除与中文编码指南
- 开发指南与数据库迁移
- 部署建议与生产配置
- 贡献指南与许可证
- 变更日志

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

### 环境变量详解（分类与依赖）
- LLM 与嵌入模型（兼容 OpenAI API）
  - `OPENAI_API_KEY`：API 密钥（可使用 SiliconFlow 的密钥）
  - `OPENAI_BASE_URL`：API 基础地址，SiliconFlow 为 `https://api.siliconflow.cn/v1`
  - `OPENAI_MODEL`：对话/指令模型，推荐 `Qwen/Qwen2.5-7B-Instruct`
  - `OPENAI_EMBEDDING_MODEL`：嵌入模型，如 `BAAI/bge-m3`
  - `OPENAI_MAX_TOKENS`：生成最大 tokens（默认 1000）
  - `OPENAI_TEMPERATURE`：采样温度（默认 0.7）
  - 替代字段（可选）：`SILICONFLOW_API_KEY`、`SILICONFLOW_BASE_URL`（与以上字段完全兼容）
- 向量数据库
  - `VECTOR_DB_TYPE`：`chroma` 或 `pinecone`
  - `CHROMA_PERSIST_DIRECTORY`：本地 ChromaDB 持久化目录
  - `PINECONE_API_KEY`、`PINECONE_ENVIRONMENT`、`PINECONE_INDEX_NAME`：使用 Pinecone 时必需
- 应用与日志
  - `HOST`、`PORT`、`RELOAD`：服务监听与热重载
  - `SECRET_KEY`：应用密钥（会话/安全相关）
  - `DEBUG`、`LOG_LEVEL`：调试与日志等级
  - `ENABLE_STRUCTURED_LOGGING`、`STRUCTURED_LOG_FILE`：结构化日志输出（JSON 事件）
  - `ENABLE_AUTO_RESTART`：失败时是否自动重启（默认关闭）
- 文档摄取与嵌入
  - `PREPARE_ONLY`：仅生成分块，不写入向量库（可在 `ingest.py` 中使用）
  - `REBUILD_VECTOR_DB`：重建向量库（清库后重建）
  - `DOC_BATCH_SIZE`：批处理大小（嵌入脚本使用）
  - `USE_LOCAL_EMBEDDINGS`：使用本地嵌入模型（离线环境）
- OCR（Windows）
  - `TESSERACT_CMD`：Tesseract 可执行文件路径
  - `OCR_LANG`：语言包设置，如 `chi_sim+eng`
- 测试与工具
  - `BASE_URL`：测试脚本请求的基础地址（默认 `http://localhost:8000`，可在运行 `tools/test_api.py` 前设置）
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
- `GET /api/v1/queries/history` - 获取查询历史（支持分页与计数）
- `GET /api/v1/queries/history/{id}` - 获取查询详情
- `POST /api/v1/queries/history/{id}/feedback` - 提交反馈
- `GET /api/v1/queries/statistics` - 查询统计
- `POST /api/v1/queries/batch` - 批量查询

#### 请求参数（ask）
- `question`：字符串，必填；用户自然语言问题。
- `query_type`：字符串，选填；`general`（默认）、`regulatory`（建议在明确监管相关的场景使用）。
- `max_chunks`：整数，选填；用于上下文组装的最大片段数（默认 5）。
- `top_k`：整数，选填；语义检索返回的候选数量（默认 8）。
- `language`：字符串，选填；期望回答语言（如 `zh`）。
- `return_sources`：布尔，选填；是否返回 `retrieved_chunks` 来源详情（默认 true）。

示例：
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "question": "这份保险的保障范围是什么？",
    "query_type": "general",
    "max_chunks": 5,
    "top_k": 8,
    "return_sources": true
  }'
```

#### 返回字段说明（更新）
- `/api/v1/queries/ask` 响应包含：`query_id`、`question`、`answer`、`query_type`、`response_time`、`chunks_used`、`retrieved_chunks`、`confidence_score` 等。
  - 当模型/API Key 缺失或上游失败时，仍会返回非空的 `query_id`，`answer` 为友好错误提示，`retrieved_chunks` 为空列表。
- `/api/v1/queries/history` 返回 `QueryHistoryListResponse` 对象：
  - `items`：`QueryHistoryResponse[]` 列表，每项包含 `id`、`question`、`answer`、`query_type`、`response_time`、`chunks_used`、`similarity_scores`、`created_at`、`metadata`。
  - `total_count`：满足筛选条件的历史记录总数（与分页无关）。
  - 每个 `items` 项的 `metadata` 中包含：`rewritten_query`（查询改写结果）、`rewriting_metadata`（改写过程元数据）、`retrieved_chunks`（检索片段及相似度与审计信息）。

示例：
```json
{
  "items": [
    {
      "id": 123,
      "question": "这份保险的保障范围是什么？",
      "answer": "生成的回答或友好错误提示",
      "query_type": "general",
      "response_time": 7.42,
      "chunks_used": 5,
      "similarity_scores": [0.81, 0.77, 0.74],
      "created_at": "2025-11-12T16:20:00Z",
      "metadata": {
        "rewritten_query": "该问题的优化改写",
        "rewriting_metadata": {"primary_search_intent": "保障范围", "query_vectors": [/*...*/]},
        "retrieved_chunks": [
          {
            "chunk_id": "...",
            "document_id": "...",
            "document_name": "...",
            "content": "...",
            "page_number": 2,
            "similarity_score": 0.83,
            "metadata": {
              "ranking_details": {"final_score": 0.86},
              "effective_date": "2024-10-01"
            }
          }
        ]
      }
    }
  ],
  "total_count": 66
}
```

计数专用用法：
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/queries/history?count_only=true"
# 返回：{"items":[],"total_count":<满足筛选条件的总数>}
```

分页与筛选示例：
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/queries/history?skip=0&limit=50&query_type=general"
```

#### 响应模型详解（ask 示例）
```json
{
  "query_id": 23,
  "question": "这份保险的保障范围是什么？",
  "answer": "该问题需要模型生成，若上游不可用则返回友好错误提示。",
  "query_type": "general",
  "response_time": 7.42,
  "chunks_used": 5,
  "retrieved_chunks": [
    {
      "doc_id": "policy-2024-A",
      "chunk_id": 118,
      "score": 0.83,
      "content_preview": "本保险的保障范围包含住院医疗、重疾、意外...",
      "metadata": {"effective_date": "2024-10-01", "product_type": "health"}
    }
  ],
  "confidence_score": 0.76,
  "metadata": {
    "rewritten_query": "该保单保障范围？",
    "rewriting_metadata": {"model": "Qwen/Qwen2.5-7B-Instruct"}
  }
}
```

字段要点：
- `query_id`：持久化的查询记录主键，异常路径也保证非空（见下文）。
- `retrieved_chunks`：返回命中的文档片段及相似度与元数据，便于追溯与可视化。
- `metadata.rewritten_query`：在 RAG 前置步骤进行轻量改写，以提升检索质量。

#### 错误与异常处理细则
- 缺失/错误的模型 API Key：返回友好错误信息；`query_id` 非空；`retrieved_chunks` 为空；`metadata.rewritten_query` 与 `rewriting_metadata` 为空。
- 上游模型超时/不可用：同上，记录错误上下文以便排障。
- 嵌入维度不匹配：检索可能报错；建议检查集合维度与嵌入模型配置。
- 向量数据库不可用：返回错误提示，`query_id` 仍持久化；建议先运行 `tools/check_db.py`。
- 输入校验失败：返回 400 与具体字段错误；不写入历史。

#### 简单验证（Smoke Test）
```bash
# 1) 提交查询（确保 query_id 非空）
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"question":"测试：没有API密钥时也应返回 query_id","query_type":"general"}'

# 2) 查看历史列表（items 列表与 total_count 统计）
curl -X GET "http://127.0.0.1:8000/api/v1/queries/history"

# 3) 仅获取历史总数（不返回 items）
curl -X GET "http://127.0.0.1:8000/api/v1/queries/history?count_only=true"
```

或使用测试脚本：
```bash
# 可通过环境变量设置 BASE_URL（默认 http://localhost:8000）
set BASE_URL=http://localhost:8000  # Windows PowerShell 使用 $env:BASE_URL
python tools/test_api.py
```

#### 流式问答（/api/v1/queries/ask/stream）

流式接口用于边检索边生成，事件按行输出，便于前端实时展示：
- `start`：开始事件，携带 `query_id` 与初始上下文信息。
- `context`：检索事件，包含 `retrieved_chunks` 原始片段列表（`doc_id`/`chunk_id`/`score`/`content_preview`/`metadata`）。
- `token`：生成过程中的增量 token。
- `end`：结束事件，包含完整 `answer` 与统计信息（如 `response_time`/`chunks_used`）。
- `error`：错误事件（如检索为空时的提示）。

示例（Windows）：
```bash
curl.exe -X POST "http://127.0.0.1:8000/api/v1/queries/ask/stream" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "question": "比较重疾险与医疗险的保障差异",
    "query_type": "general",
    "similarity_threshold": 0.5,
    "max_chunks": 6,
    "include_metadata": true
  }'
```
提示：请避免使用会截断 SSE 的管道/分页；若仅调试检索，可关注 `context` 事件中的 `retrieved_chunks`。

### 兼容性与前端适配

- 历史接口字段从早期预览版的 `Count` 统一为 `total_count`。请前端改用 `total_count`；如需兼容旧结构，可同时回退读取 `Count`。
- 前端示例（兼容处理）：
```js
const res = await fetch('/api/v1/queries/history');
const data = await res.json();
const items = data.items ?? data.history ?? (Array.isArray(data) ? data : []);
const total = data.total_count ?? data.Count ?? (Array.isArray(items) ? items.length : 0);
```

### 多轮对话与 session_id 使用

- `session_id`：可选字符串，用于标识同一会话线程，并在改写阶段携带该会话的近期聊天历史。
- 历史窗口：最多保留最近 10 轮的用户/助手消息，合并后再截断至 4000 字符，保证提示安全性与可控成本。
- 改写用途：历史仅用于查询改写（QueryRewriterService），不改变持久化的原始 `question` 字段；改写结果写入 `metadata.rewritten_query`，改写的结构化元数据写入 `metadata.rewriting_metadata`（来源于数据库列 `QueryHistory.rewriting_metadata_json`）。
- 开启方式：在 `.env` 或环境变量中设置 `ENABLE_QUERY_REWRITING=true`，并确保 `ONTOLOGY_JSON_PATH=tools/insurance_ontology.json` 可读。

示例（非流式）：
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "question": "这份保险的保障范围是什么？",
    "query_type": "general",
    "session_id": "uuid-会话-001"
  }'
```

示例（流式）：
```bash
curl.exe -X POST "http://127.0.0.1:8000/api/v1/queries/ask/stream" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "question": "比较重疾险与医疗险的保障差异",
    "query_type": "general",
    "max_chunks": 6,
    "session_id": "uuid-会话-001",
    "include_metadata": true
  }'
```

返回体中的会话与改写字段：
- `metadata.rewritten_query`：当前问题的轻量改写，用于提升检索质量；可能为 `null`（当未启用改写时）。
- `metadata.rewriting_metadata`：结构化改写元信息（由 `QueryHistory.rewriting_metadata_json` 解析而来）；当未启用改写时为 `null`。
- `QueryHistory.session_id`：数据库中记录会话标识，便于多轮追踪与统计（不直接出现在响应模型中）。

注意：即使未启用改写，`session_id` 也会被持久化；当启用改写后，历史会被用于提示构造（10 轮 + 4000 字符上限）。

#### 检索阈值建议与批量测试示例

基于本地测试：
- 监管类/规范类问题：推荐 `similarity_threshold=0.5–0.7`（更严格、命中更精准）。
- 产品比较/一般性问题：推荐 `0.35–0.5`（更宽松、提高召回）。

批量对比示例（非流式接口）：
```bash
# 低阈值（提高召回，可能有噪声）
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "question": "中国银行保险监督管理委员会对健康险产品的最新规定有哪些？",
    "query_type": "regulatory",
    "similarity_threshold": 0.35,
    "max_chunks": 6,
    "include_metadata": true
  }'

# 高阈值（更严格，更适合监管类精准问答）
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "question": "中国银行保险监督管理委员会对健康险产品的最新规定有哪些？",
    "query_type": "regulatory",
    "similarity_threshold": 0.7,
    "max_chunks": 6,
    "include_metadata": true
  }'
```
返回中可关注 `chunks_used`、`confidence_score` 与 `retrieved_chunks` 内容差异，以评估阈值设置的影响。

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

### 关键模块职责
- `app/core/rag_workflow.py`：RAG 处理管线（改写、检索、重排、组装、生成）。
- `app/services/query_service.py`：查询问答服务，负责端到端处理与异常路径持久化。
- `app/services/vector_store.py`：向量库封装与检索接口。
- `app/services/llm_service.py`：模型调用封装（兼容 OpenAI API）。
- `app/models/schemas.py`：Pydantic 请求/响应模型定义。
- `app/core/structured_logger.py`：结构化日志记录与事件埋点。

## 🔍 使用示例

### 1. 智能问答

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/queries/ask" \
  -H "Content-Type: application/json; charset=utf-8" \
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

## 🧠 RAG 工作流详解
- 第 0 步：预处理与嵌入（离线）
  - 文档分块（`scripts/embed_chunks.py` / `ingest.py`）
  - 生成嵌入并写入向量库（Chroma/Pinecone）
- 第 1 步：查询理解与改写
  - 轻量改写（`metadata.rewritten_query`）以提升召回与相关性
- 第 2 步：语义检索
  - 基于向量相似度返回候选片段（`retrieved_chunks`）
- 第 2.5 步：监管关联重排序
  - 对监管相关且与查询高度关联的文档施加固定加分，结合时效性重排
- 第 3 步：上下文选择与组装
  - 基于分数/覆盖度选择 `chunks_used` 个片段，组装上下文
- 第 4 步：答案生成
  - 使用指令模型生成回答与引用说明（若启用）
- 第 5 步：后处理与持久化
  - 记录耗时、置信度、来源片段与查询历史（异常路径亦持久化）

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

## 🧪 测试与验证

### 快速运行
```bash
# 运行所有 API 端点测试（自动包含 query_id 异常路径保证与历史增长自检）
python tools/test_api.py
```

### 测试细节
- 新增自检：
  - `ask` 在异常路径（模型/API Key 不可用）也返回非空 `query_id`
  - 历史列表在 `ask` 后计数增加，并能找到对应 `query_id`
- 可配置：通过 `BASE_URL` 环境变量修改测试目标（默认 `http://localhost:8000`）

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

### 异常路径与 query_id 保证
- 为了便于问题追踪与反馈统计，系统在异常路径也会持久化查询历史并返回非空的 `query_id`。
- 当模型/API Key 缺失或上游调用失败时：
  - `/api/v1/queries/ask` 的 `answer` 为友好错误提示，`retrieved_chunks` 为空列表，`query_id` 仍非空；
  - `/api/v1/queries/history` 中对应项的 `metadata.rewritten_query` 与 `metadata.rewriting_metadata` 为空，`metadata.retrieved_chunks` 为空列表。
- 如出现 `query_id = null`：请确认更新至最新代码版本并检查服务日志是否存在未捕获异常；必要时重启服务。

### 编码与本地化（深入指南）
- 推荐统一 `UTF-8`：服务端与客户端均应设置 `charset=utf-8`。
- Windows PowerShell：
  - `chcp 65001` 切换到 UTF-8 代码页（必要时）
  - `$env:PYTHONIOENCODING = "utf-8"` 保证 Python 输出编码一致
- 前端：确保 `index.html` 使用 `<meta charset="utf-8">`，后端响应头为 `application/json; charset=utf-8`。

### 中文乱码显示排查
- API 客户端与服务端应统一为 UTF-8：将请求头设置为 `Content-Type: application/json; charset=utf-8`。
- 在 Windows PowerShell 终端中，建议执行：
  - `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
  - 使用 `Invoke-RestMethod` 时显式设置 `-ContentType 'application/json; charset=utf-8'`
- FastAPI 默认使用 UTF-8 编码；若前端页面出现乱码，请确认 `static/index.html` 包含 `<meta charset="utf-8">`。

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

## 🛠 监控与日志
- 健康端点：`/api/v1/health/live`、`/api/v1/health/ready`、`/api/v1/health/model`
- 结构化日志：启用后以 JSON 事件记录关键动作（请求、错误、性能）
- 日志轮转：建议生产环境配置按大小或按日轮转（Nginx/系统级工具）

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## � 变更日志
- 2025-11-10
  - 解析参数弃用修复：`partition_pdf` 仅传 `languages`，弃用 `ocr_languages`。`ingestion_config.yml` 改为 `parser.languages`，并在代码中保留向后兼容以避免双参数告警。
  - 依赖稳定化：固定 `unstructured==0.18.18`、`unstructured-inference==0.7.34`，解决第三方内部 `password` 误告警与不兼容问题（与 Python 3.13 兼容）。
  - 验证脚本修复：`scripts/validate_retrieval.py` 支持 `--k`/`--top_k` 参数；日志初始化改为 `setup_logging(log_level=...)`；执行后输出检验报告路径。
  - 快速检索验证：`python scripts\\validate_retrieval.py --question "什么是车险免赔额？" --k 5 --output data\\vector_db\\chroma\\retrieval_verification.json`。
  - 仅解析模式（不写库）：Windows 下可 `set PREPARE_ONLY=1 && set REBUILD_VECTOR_DB=0 && python ingest.py`，用于观察解析告警与性能。
  - 故障排除：若出现 `PyMuPDF` 编译错误（Windows 缺少 VS 工具链），请保留现有已编译版本或安装预编译二进制；OCR 回退需确保 `TESSERACT_CMD` 指向正确。
- 2025-11-09
  - 查询服务：新增 `RetrievedChunk` 规范化，兼容 `doc_id/document_id`、`chunk_id/id`、`score/similarity_score`，相似度分数钳制到 `[0,1]`，保证 `metadata` 为字典；异常路径不再触发 422 校验错误。
  - 响应与历史：`/api/v1/queries/ask` 同步响应与历史记录均包含 `retrieved_chunks`（为空时返回空数组）；确认 `metadata.rewritten_query` 与 `rewriting_metadata` 在不可用路径下为 `null` 的行为并记录。
  - 流式接口：补充 `/api/v1/queries/ask/stream` 事件说明（`start/context/token/end/error`），并在文档中增加示例，`context` 事件携带原始检索片段用于前端可视化。
  - 端口与前端：统一本地运行端口为 `8000`，根路径 `/` 正常返回前端预览页面，验证事件流无报错。
  - 阈值建议：基于批量与流式测试，建议监管类问题使用 `similarity_threshold=0.5–0.7`，产品比较/一般问题使用 `0.35–0.5`；示例命令与脚本说明已补充。
  - 编码兼容：为 `curl` 示例统一添加 `charset=utf-8` 以减少中文乱码；在 Windows 终端中建议使用 `curl.exe` 并避免管道截断 SSE 事件。
  - 健康检查：说明 `GET /api/v1/health/ready` 可能显示 `not_ready`（向量服务预热/索引初始化标志未就绪），不影响正常查询与生成；以 `live` 与整体健康结果为准。
- 2025-11-08
  - `query_service.process_query` 异常路径持久化查询历史并保证返回非空 `query_id`
  - `tools/test_api.py` 增加 `query_id` 与历史增长自检，支持 `BASE_URL` 环境变量
  - README 扩展：响应模型详解、RAG 工作流、环境变量分类与编码指南

## �📄 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 支持

如有问题或建议，请：

1. 查看文档和FAQ
2. 搜索已有的Issues
3. 创建新的Issue
4. 联系开发团队

---

**InsurIntellect Agent** - 让保险文档问答更智能！
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

## 数据维护与全量回填（2025-11-05）

为保证文档日期元数据完整与质量可控，已在本地启动一次“最完整的全量回填”流程，并对报告与复盘方式进行梳理。

- 运行命令（完整管线）
  - `python scripts/backfill_metadata.py --batch-size 1000 --workers 12 --max-content-chars 12000 --neighbor-window 700 --report-dir reports`
  - 说明：优先使用档案官提取接口，其次结合启发式邻近标签抽取；并行 workers=12，批大小 1000，邻近窗口 700 字符，限制每段最大字符数 12000。

- 前置条件
  - 档案官提取网关需可用：`http://127.0.0.1:8001/archiver/extract-dates`
  - 若外部档案官不可用，可改用 `--fallback` 走启发式本地回退（覆盖面可能略低）。

- 报告输出
  - 报告目录：`reports/`
  - 命名规则：`backfill_report_YYYYMMDD_HHmmss.json` 与同名 `.html` 汇总（若启用），示例：`reports/backfill_report_20251105_215044.json`
  - 读取最新报告：`python scripts/read_latest_report.py`

- 失败重试与增量
  - 失败重试：`python scripts/backfill_metadata.py --retry-failed-from <上次报告.json> --batch-size 500 --workers 8 --report-dir reports`
  - 条件过滤（一次性修补指定范围）：`--where-json '{"source":"pdf","vendor":"XXX"}'`
  - 增量及时性修复：`python scripts/run_timeliness_recovery.py --report-dir reports --neighbor-window 700 --max-content-chars 12000`

- 当前状态
  - 已按上述完整参数启动全量回填，报告将生成于 `reports/` 目录；生成后可用 `scripts/read_latest_report.py` 查看摘要，并在本 README 的“维护与测试变更记录”中补充本次结果。

- 复现与验证
  - 清空旧报告：`PowerShell: Remove-Item reports\* -Recurse -Force`
  - 启动回填：见“运行命令”一节；建议在应用或网关就绪后再执行，避免连接失败。
  - 阅读摘要：`python scripts/read_latest_report.py`
  - 汇总报告：`python scripts/report_backfill.py --report-dir reports`

> 注：若在 CI 中运行，建议同时生成机器可读 JSON 与简要 Markdown，以便后续统计。同时可在测试脚本中加入网关就绪轮询与重试，以降低临时不可用对结果的影响。
## 前端事件绑定与约定

为避免重复触发与脚本逻辑冲突，前端事件统一在 `static/js/app.js` 中完成绑定，页面 HTML 不再使用内联事件（如 `onclick`、`oninput`、`onkeydown`）。核心约定如下：

- 统一入口：在 `DOMContentLoaded` 中调用：
  ```js
  document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    initializeTheme();
  });
  ```
- 文本输入框：
  - 元素：`#chat-input`
  - 自动高度：`adjustTextareaHeight()` 在 `input` 事件中绑定
  - 回车发送：`handleKeyDown()` 处理（`Shift+Enter` 换行，`Enter` 发送）
  - 计数显示：`updateCharCounter()`（如界面包含字符计数器）
- 统一绑定的按钮与选择器（在 `setupEventListeners()` 中）：
  - `#toggle-sidebar-btn`：展开/折叠侧栏
  - `#new-chat-btn`：新建对话
  - `#clear-history-btn`：清空历史
  - `#export-chat-btn`：导出聊天记录
  - `#share-chat-btn`：分享（预留占位函数 `shareChat()`）
  - `#open-settings-btn`：打开设置
  - `#toggle-theme-btn`：主题切换（深/浅色）
  - `#cancel-stream-btn`：取消当前流式响应
  - `#send-btn`：发送当前输入
- 提示/示例按钮：使用 `data-prompt` 属性标注提示内容，示例：
  ```html
  <button class="prompt-chip" data-prompt="理赔需要哪些材料？">理赔材料清单</button>
  ```
  在脚本中统一绑定：
  ```js
  document.querySelectorAll('[data-prompt]').forEach(btn => {
    btn.addEventListener('click', () => {
      const prompt = btn.getAttribute('data-prompt') || '';
      applyPromptSuggestion(prompt);
    });
  });
  ```
- 不再加载 `static/js/script.js`（其中包含另一套 UI 逻辑，可能与 `app.js` 重叠）；若确需从中保留函数，请将所需逻辑迁移到 `app.js` 并在 `setupEventListeners()` 中统一绑定。
- 常见错误与修复：
  - `ReferenceError: autoResizeTextarea is not defined`
    - 原因：HTML 使用了 `oninput="autoResizeTextarea(this)"`，而页面仅加载了定义 `adjustTextareaHeight()` 的 `app.js`
    - 解决：移除所有内联事件，由 `setupEventListeners()` 绑定 `input` 事件并调用 `adjustTextareaHeight()`

简单验收步骤：
- 启动服务并打开 `http://127.0.0.1:8000/`
- 输入框随输入自动增高，无控制台错误
- 侧栏按钮、主题切换、示例提示按钮均可正常工作

---

## 变更日志

- 2025-11-12（docs/frontend）：统一前端事件绑定至 `static/js/app.js`，移除 HTML 内联事件；修复 `autoResizeTextarea` 引用错误；采用 `adjustTextareaHeight()` 处理文本域自适应。
- 2025-11-12（docs/api）：`GET /api/v1/queries/history` 文档统一为 `QueryHistoryListResponse`（`items` + `total_count`）；新增 `count_only=true` 用法与示例；前端兼容旧字段 `Count` 的读取，建议优先使用 `total_count`。
