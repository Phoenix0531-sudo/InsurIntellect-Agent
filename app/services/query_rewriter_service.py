# -*- coding: utf-8 -*-
"""
查询重写服务（SRP）
负责：提示词构建、聊天历史与领域本体注入，调用 LLMService 执行重写。
"""

from __future__ import annotations
from typing import Optional, Dict, Any
from functools import lru_cache
import json

from app.core.config import settings
from app.core.app_logging import get_logger
from app.services.llm_service import LLMService
from app.prompts import QUERY_REWRITER_PROMPT_TEMPLATE

logger = get_logger(__name__)


class QueryRewriterService:
    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self.llm = llm_service or LLMService()

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_ontology_text() -> str:
        """加载保险术语本体库为紧凑文本（JSON字符串），失败时返回空对象字符串。"""
        try:
            with open(settings.ONTOLOGY_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"加载本体库失败，使用空本体：{e}")
            return "{}"

    async def rewrite_query(self, user_query: str, chat_history: Optional[str] = None) -> Dict[str, Any]:
        """
        重写用户查询为可检索的结构化语句，注入聊天历史与领域本体。
        - chat_history 使用最近10轮（由调用方负责），此处仅做 4000 字符安全截断。
        - 严格要求 LLM 输出单一 JSON。
        """
        ontology_text = self._load_ontology_text()
        chat_text = (chat_history or "").strip()
        # 安全截断：保留最近部分，避免提示过长影响 token
        if len(chat_text) > 4000:
            chat_text = chat_text[-4000:]

        prompt = QUERY_REWRITER_PROMPT_TEMPLATE.format(
            chat_history=chat_text or "（无历史记录）",
            user_query=user_query,
            ontology=ontology_text,
        )

        messages = [
            {"role": "system", "content": "你是严谨的查询重写架构师，严格输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            resp = await self.llm.agenerate_structured_decision(messages, temperature=0.2, max_tokens=512)
            raw = resp.choices[0].message.content if resp and getattr(resp, "choices", None) else ""
            cleaned = (raw or "").strip()
            # 清理可能的 Markdown 代码块包装
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned[4:]
            result = json.loads(cleaned)
            return result
        except Exception as e:
            logger.error(f"查询重写失败，回退到原始查询：{e}")
            return {
                "original_query": user_query,
                "independent_query": user_query,
                "primary_search_intent": "",
                "query_vectors": [{"title": "原始", "query": user_query}],
                "micro_ontology": {},
            }

