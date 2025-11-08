# Embedding保险场景评测报告

- 生成时间: 2025-11-06 20:35:50
- 全局随机种子: `42`
- Chroma 路径: `./data/vector_db/chroma`

**数据集概览**
- 文档数: 36
- 查询数: 18
- 每查询相关文档数: 2

**模型结果**
- 模型 `bge-large-zh-v1.5` （维度 1024，集合 `benchmark_bge_large_zh_v1_5`）
  - Recall@5: 0.1944 | Recall@10: 0.3333 | Recall@20: 0.6111 | MRR: 0.2681
- 模型 `gte-Qwen1.5-7B-instruct` （维度 1024，集合 `benchmark_gte_Qwen1_5_7B_instruct`）
  - Recall@5: 0.1667 | Recall@10: 0.2778 | Recall@20: 0.5278 | MRR: 0.2041
- 模型 `text-embedding-ada-002` （维度 1536，集合 `benchmark_text_embedding_ada_002`）
  - Recall@5: 0.1389 | Recall@10: 0.2500 | Recall@20: 0.4444 | MRR: 0.2638

**结论与建议**
- 本报告基于存根模型的确定性向量，数值仅用于流程与指标验证。
- 替换为真实嵌入模型后，保持集合独立以避免维度/空间混淆。
- 扩充查询与标注可提高评测稳定性；建议每查询≥2个相关文档。