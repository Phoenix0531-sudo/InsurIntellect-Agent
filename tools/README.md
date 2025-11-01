# 工具和测试文件夹

本文件夹包含项目的测试文件和维护工具脚本。

## 测试文件

### API测试
- **`test_api.py`** - API端点功能测试
- **`test_rag_workflow.py`** - RAG工作流测试
- **`test_web_interface.py`** - Web界面功能测试

### 数据库检查
- **`check_db.py`** - 数据库状态检查工具

## 维护工具

### ChromaDB管理工具
- **`check_chromadb_metadata.py`** - 检查ChromaDB集合的元数据信息
- **`check_embedding_dimensions.py`** - 检查嵌入模型维度和ChromaDB集合维度匹配情况
- **`reset_chromadb.py`** - 重置ChromaDB集合（保留数据目录）
- **`force_reset_chromadb.py`** - 强制重置ChromaDB（完全删除数据目录）

### 系统维护工具
- **`reset_agent.py`** - 重置代理实例

## 使用说明

### 运行测试
```bash
# 运行API测试
python tools/test_api.py

# 运行RAG工作流测试
python tools/test_rag_workflow.py

# 运行Web界面测试
python tools/test_web_interface.py
```

### 数据库维护
```bash
# 检查数据库状态
python tools/check_db.py

# 检查ChromaDB元数据
python tools/check_chromadb_metadata.py

# 检查嵌入维度
python tools/check_embedding_dimensions.py

# 重置ChromaDB集合
python tools/reset_chromadb.py

# 强制重置ChromaDB（谨慎使用）
python tools/force_reset_chromadb.py

# 重置代理实例
python tools/reset_agent.py
```

## 注意事项

1. **测试文件**：用于验证系统功能，可以定期运行确保系统正常工作
2. **检查工具**：用于诊断问题，不会修改数据
3. **重置工具**：会修改或删除数据，使用前请确保已备份重要数据
4. **强制重置**：`force_reset_chromadb.py` 会完全删除向量数据库，请谨慎使用

## 开发建议

- 新增测试文件时，请遵循现有的命名规范
- 新增维护工具时，请添加相应的使用说明
- 定期运行测试文件，确保系统功能正常
- 使用重置工具前，请先尝试检查工具诊断问题