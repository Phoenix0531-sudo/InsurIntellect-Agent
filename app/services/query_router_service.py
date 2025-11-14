"""
查询路由器服务
根据用户查询将其路由到 RAG 或 SQL。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.core.app_logging import get_logger
from app.services.llm_service import LLMService

logger = get_logger(__name__)


ROUTER_PROMPT = (
    "你是一个严格的`查询路由器`。\n"
    "你的任务：根据用户的自然语言问题，决定使用 RAG（语义检索+生成）还是 SQL（结构化查询）来回答。\n\n"
    "可用的结构化数据库表：`document_metadata`，其模式如下：\n"
    "- chunk_id: TEXT（文档块的稳定唯一ID）\n"
    "- product_name: TEXT（产品名称）\n"
    "- effective_date: TEXT（生效日期，字符串形式）\n"
    "- document_type: TEXT（文档类型，如条款、说明书、费率）\n"
    "- status: TEXT（active, expired, abolished 等）\n\n"
    "路由规则：\n"
    "- 选择`RAG`：当问题属于语义、比较、定义、解释、概述、复杂推理等。\n"
    "  例：‘这两个产品有什么区别？’、‘解释免责条款的涵义’，‘如何理解这个保险术语？’\n"
    "- 选择`SQL`：当问题属于事实、列表、计数、筛选、日期范围、状态过滤等。\n"
    "  例：‘列出已废止的产品’，‘统计 2021 年生效的条款数量’，‘哪些文档类型是费率？’\n\n"
    "当选择`SQL`时，你必须生成一条只读的 SELECT 语句，且仅查询 `document_metadata`。\n"
    "禁止任何非只读语句（如 INSERT/UPDATE/DELETE/ALTER/DROP/TRUNCATE/CREATE/ATTACH/PRAGMA/VACUUM）。\n"
    "SQL 应当是简单安全的单条语句，可包含 WHERE/ORDER BY/LIMIT。\n\n"
    "输出格式（严格 JSON，无额外文本）：\n"
    "- RAG 路由时：{\"route\": \"RAG\", \"query\": \"原始用户问题文本\"}\n"
    "- SQL 路由时：{\"route\": \"SQL\", \"query\": \"SELECT ... FROM document_metadata WHERE ...\"}\n"
    "仅输出上述 JSON 对象，不要输出解释、Markdown或代码块。"
)


class QueryRouterService:
    """RAG/SQL 路由器服务。"""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm = llm_service or LLMService()

    @staticmethod
    def _clean_json_str(s: str) -> str:
        # 去除可能的代码围栏和多余空白
        s = s.strip()
        s = re.sub(r"^```(?:json)?\n|\n```$", "", s)
        return s.strip()

    async def route_query(self, query: str) -> Dict[str, Any]:
        """调用 LLM 进行路由，返回 {route, query}。解析失败时回退到 RAG。"""
        try:
            messages = [
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": f"用户查询：{query}\n仅输出JSON对象。"},
            ]
            resp = await self.llm.agenerate_structured_decision(messages, temperature=0.0, max_tokens=256)
            content = resp.choices[0].message.content if resp and resp.choices else ""
            content = self._clean_json_str(content)
            parsed = json.loads(content)

            # 基本校验
            route = (parsed.get("route") or "").upper()
            q = parsed.get("query") or ""
            if route not in ("RAG", "SQL"):
                raise ValueError("invalid route")
            if not isinstance(q, str) or not q.strip():
                raise ValueError("missing query")

            return {"route": route, "query": q}
        except Exception as e:
            logger.warning(f"路由 JSON 解析失败，回退到 RAG：{e}")
            return {"route": "RAG", "query": query}

