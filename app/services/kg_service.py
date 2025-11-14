from __future__ import annotations

from typing import List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_logging import get_logger
from app.models.database_models import DocumentMetadata, GraphEntity, GraphRelation

logger = get_logger(__name__)


class KGService:
    """知识图谱检索服务。

    根据用户查询，从图谱或结构化元数据中提取相关事实，
    返回可直接注入到提示词中的精炼事实列表。
    """

    def _extract_terms(self, query: str) -> List[str]:
        q = (query or "").strip()
        if not q:
            return []
        # 简易分词与过滤：保留中文词片段与可能的产品名关键词
        tokens: List[str] = []
        buf = []
        for ch in q:
            if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
                buf.append(ch)
            else:
                if buf:
                    tokens.append("".join(buf))
                    buf = []
        if buf:
            tokens.append("".join(buf))

        # 仅保留长度>=2或包含“险/保险”的片段
        terms = [t for t in tokens if (len(t) >= 2 or ("险" in t or "保险" in t))]
        return list(dict.fromkeys(terms))[:6]

    async def aget_facts(self, db: AsyncSession, query: str, limit: int = 6) -> List[str]:
        """返回与查询相关的知识图谱事实。

        优先从 graph_entities/graph_relations 读取；若图谱为空或无命中，
        回退到 document_metadata 聚合信息。
        """
        try:
            terms = self._extract_terms(query)
            facts: List[str] = []

            # 1) 优先尝试图谱：匹配 Product 类实体
            try:
                if terms:
                    stmt = select(GraphEntity).where(GraphEntity.entity_type == "Product")
                    # LIKE 任意一个 term
                    like_clauses = []
                    for t in terms:
                        like_clauses.append(GraphEntity.name.ilike(f"%{t}%"))
                    if like_clauses:
                        from sqlalchemy import or_
                        stmt = stmt.where(or_(*like_clauses))

                    res = await db.execute(stmt)
                    product_entities = res.scalars().all()
                else:
                    product_entities = []
            except Exception as e:
                logger.warning(f"图谱查询失败，回退到元数据：{e}")
                product_entities = []

            if product_entities:
                for pe in product_entities[:limit]:
                    # 取该产品关联的文档类型关系
                    rel_stmt = select(GraphRelation).where(
                        GraphRelation.source_entity_id == pe.id,
                        GraphRelation.relation_type == "HAS_DOCUMENT_TYPE",
                    )
                    rel_res = await db.execute(rel_stmt)
                    rels = rel_res.scalars().all()

                    doc_types: Dict[str, int] = {}
                    for r in rels:
                        try:
                            # 获取目标实体（DocumentType）名称
                            tgt_stmt = select(GraphEntity).where(GraphEntity.id == r.target_entity_id)
                            tgt_res = await db.execute(tgt_stmt)
                            tgt = tgt_res.scalar_one_or_none()
                            if tgt:
                                doc_types[tgt.name] = doc_types.get(tgt.name, 0) + 1
                        except Exception:
                            pass

                    # 从结构化元数据取生效日期聚合（辅助事实）
                    eff_stmt = (
                        select(DocumentMetadata.effective_date, func.count(DocumentMetadata.id))
                        .where(DocumentMetadata.product_name == pe.name)
                        .group_by(DocumentMetadata.effective_date)
                    )
                    eff_res = await db.execute(eff_stmt)
                    eff_rows = [(r[0], r[1]) for r in eff_res.fetchall()]
                    eff_desc = ", ".join(
                        [f"{d or '未知'}({c}条)" for d, c in eff_rows[:3]]
                    ) if eff_rows else "未知"

                    if doc_types:
                        types_desc = ", ".join([f"{k}({v}块)" for k, v in doc_types.items()])
                        facts.append(f"产品『{pe.name}』关联文档类型：{types_desc}；生效日期分布：{eff_desc}")
                    else:
                        facts.append(f"产品『{pe.name}』已在文档中出现；生效日期分布：{eff_desc}")

                if facts:
                    return facts[:limit]

            # 2) 回退：直接从 document_metadata 匹配产品名并聚合
            if terms:
                from sqlalchemy import or_
                like_clauses = [DocumentMetadata.product_name.ilike(f"%{t}%") for t in terms]
                dm_stmt = (
                    select(
                        DocumentMetadata.product_name,
                        DocumentMetadata.document_type,
                        func.count(DocumentMetadata.id),
                        func.min(DocumentMetadata.effective_date),
                    )
                    .where(or_(*like_clauses))
                    .group_by(DocumentMetadata.product_name, DocumentMetadata.document_type)
                    .order_by(func.count(DocumentMetadata.id).desc())
                )
            else:
                dm_stmt = (
                    select(
                        DocumentMetadata.product_name,
                        DocumentMetadata.document_type,
                        func.count(DocumentMetadata.id),
                        func.min(DocumentMetadata.effective_date),
                    )
                    .group_by(DocumentMetadata.product_name, DocumentMetadata.document_type)
                    .order_by(func.count(DocumentMetadata.id).desc())
                )

            dm_res = await db.execute(dm_stmt)
            rows = dm_res.fetchall()
            by_product: Dict[str, Dict[str, Any]] = {}
            for prod, dtype, cnt, min_eff in rows:
                if not prod:
                    continue
                entry = by_product.setdefault(prod, {"types": {}, "min_eff": min_eff})
                entry["types"][dtype or "未知"] = int(cnt)
                if entry["min_eff"] is None and min_eff is not None:
                    entry["min_eff"] = min_eff

            for prod, info in list(by_product.items())[:limit]:
                types_desc = ", ".join([f"{k}({v}块)" for k, v in info["types"].items()])
                facts.append(f"产品『{prod}』关联文档类型：{types_desc}；最早生效日期：{info['min_eff'] or '未知'}")

            return facts[:limit]
        except Exception as e:
            logger.warning(f"KG事实生成失败：{e}")
            return []

