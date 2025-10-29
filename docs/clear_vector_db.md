# 清空向量库（一键清库）

本项目提供一键清空本地 Chroma 向量库的脚本，适用于以下场景：

- 重新处理同一批文档，避免重复块；
- 调整分块、OCR 或嵌入模型策略后希望重建；
- 之前写入有误需彻底清理重来。

## 使用步骤

1. 在项目根目录执行：

   ```powershell
   python scripts/clear_vector_db.py
   ```

   该脚本会删除 `settings.CHROMA_PERSIST_DIRECTORY` 指定的持久化目录（默认 `./data/vector_db/chroma`），并重置集合 `insurance_documents`。

2. 重建向量库：

   ```powershell
   python ingest.py
   ```

   或临时清库重建：

   ```powershell
   $env:REBUILD_VECTOR_DB = "1"; python ingest.py
   ```

## 注意事项

- 此操作不可逆，会清除所有已写入的向量数据；
- 如服务正在运行（`uvicorn`），建议先停止以避免占用文件句柄；
- 仅本地 Chroma 受影响；若使用其他向量库（如 Pinecone），需按相应方式清理。

