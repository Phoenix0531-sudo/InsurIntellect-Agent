# 数据管线模式：Prepare-Only 与 Embed-Only

本项目的文档处理与向量化可以拆分为两个阶段：

- Prepare-Only：仅解析/分割/去重/提取元数据，将分割产物写入 `data/processed/chunks.jsonl`，不做嵌入与写库。
- Embed-Only：从 `data/processed/chunks.jsonl` 读取分割产物，计算嵌入并写入 Chroma 矢量库。

## 使用方法

### 1) Prepare-Only（仅准备阶段）

在 Windows PowerShell 中：

```powershell
$env:PREPARE_ONLY = "1"
python ingest.py
```

完成后会生成 `data/processed/chunks.jsonl`，每行一个块，包含：

- `id`：稳定ID（基于文件路径、页号与规范化文本的哈希）
- `text`：分割后的文本块
- `metadata`：来源文件、页码、类型、AI提取的标题等元数据

### 2) Embed-Only（仅嵌入与写库）

默认使用“远端嵌入”（通过 `OPENAI_BASE_URL` / `SILICONFLOW_BASE_URL`），如需重建矢量库可先清库或设置重建标志。

```powershell
# 可选：重建矢量库（清空后重写）
$env:REBUILD_VECTOR_DB = "1"

# 可选：控制批大小以降低速率限制风险
$env:DOC_BATCH_SIZE = "32"

python scripts/embed_chunks.py
```

如需从其他文件嵌入，或切换集合名：

```powershell
$env:CHUNKS_FILE = "data/processed/chunks.jsonl"
$env:COLLECTION_NAME = "insurance_documents"
python scripts/embed_chunks.py
```

## 远端与本地嵌入

- 远端嵌入：默认启用，使用 `settings.OPENAI_BASE_URL` 与 `settings.OPENAI_API_KEY`（或 `SILICONFLOW_BASE_URL` / `SILICONFLOW_API_KEY`）。
- 本地嵌入：如需离线，可设置 `USE_LOCAL_EMBEDDINGS=1` 并选用合适的 HuggingFace 模型（参见 `docs/siliconflow_setup.md` 中的说明）。

```powershell
# 启用本地嵌入（可选）
$env:USE_LOCAL_EMBEDDINGS = "1"
python scripts/embed_chunks.py
```

> 注意：若你暂时无法配置本地模型，保持默认的远端嵌入即可。同样建议适当调小 `DOC_BATCH_SIZE`（如 16 或 8），以降低速率限制或超时风险。

## 验证与排错

- 统计集合条数：

```powershell
python -c "from app.core.config import settings; from app.core.chromadb_manager import chroma_manager; from langchain_chroma import Chroma; vs=Chroma(client=chroma_manager.get_client(), collection_name='insurance_documents', persist_directory=settings.CHROMA_PERSIST_DIRECTORY); print(vs._collection.count())"
```

- 查看前几条文档与元数据：

```powershell
python -c "from app.core.config import settings; from app.core.chromadb_manager import chroma_manager; from langchain_chroma import Chroma; vs=Chroma(client=chroma_manager.get_client(), collection_name='insurance_documents', persist_directory=settings.CHROMA_PERSIST_DIRECTORY); res=vs._collection.get(include=['documents','metadatas'], limit=5); print(res['documents']); print(res['metadatas'])"
```

- 如果远端嵌入提示上下文限制（如 512 tokens），脚本会尝试自动回退到 `BAAI/bge-m3`。仍失败时，降低 `DOC_BATCH_SIZE` 并重试。

## 何时使用拆分模式

- 大规模文档集，嵌入阶段与准备阶段需要分离执行或并行处理。
- 经常变更嵌入模型或分割策略，希望复用已有分割产物，只重跑嵌入。
- 审计/复核需求，需将分割与元数据独立保存便于检查。

