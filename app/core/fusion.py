"""
融合算法模块
实现 Reciprocal Rank Fusion (RRF) 用于混合检索融合
"""

from typing import List, Dict, Tuple, Optional


def reciprocal_rank_fusion(rank_lists: List[List[str]], k: int = 60, top_n: Optional[int] = None) -> Tuple[List[str], Dict[str, float]]:
    """
    Reciprocal Rank Fusion (RRF)

    Args:
        rank_lists: 来自不同检索器的结果列表，每个列表按相关性降序排列（元素为 chunk_id）
        k: RRF平滑常数（默认60）
        top_n: 可选，返回的前N个结果；若为None则返回全部融合排序

    Returns:
        fused_ids: 融合后的排序列表（chunk_id）
        scores: 每个 chunk_id 的 RRF 分数字典
    """
    scores: Dict[str, float] = {}
    for rank_list in rank_lists:
        for rank, cid in enumerate(rank_list):
            # RRF 分数累加：1 / (k + rank)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)

    # 按分数降序排序；稳定排序确保相同分数时按首次出现顺序
    fused_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    if top_n is not None:
        fused_ids = fused_ids[:top_n]
    return fused_ids, scores

