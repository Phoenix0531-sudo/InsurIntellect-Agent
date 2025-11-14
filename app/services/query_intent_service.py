"""
意图分类路由器服务（KCP-FIX-4）
依赖 LLMService，对用户查询进行意图分类，并生成可用于检索阶段的元数据过滤器（metadata_filter）。
输出严格遵循 Pydantic 模型 QueryIntent 的 JSON 格式，并使用 model_validate_json 保证可靠性。
"""

from __future__ import annotations

import re
from typing import Any, Dict
from pydantic import ValidationError

from app.core.app_logging import get_logger
from app.services.llm_service import LLMService
from app.models.schemas import QueryIntent

logger = get_logger(__name__)


INTENT_PROMPT_TEMPLATE = """
你是一个严格的"RAG 策略路由器"。
任务：根据用户查询识别意图，并在需要时生成用于向量库检索的元数据过滤器（ChromaDB where）。

预定义意图与说明：
- query_coverage：用户询问保障范围、免责、理赔责任等，适合检索‘条款’。
- claims_process：用户询问理赔流程、所需材料、时效等，适合检索‘理赔’或‘理赔指南’。
- product_comparison：用户比较不同产品或方案，适合检索‘说明书’或‘费率表’。
- general：一般性问题或无法判定意图。

元数据过滤器生成规则（示例映射）：
- 若 intent = query_coverage，则 metadata_filter = {{"document_type": "条款"}}
- 若 intent = claims_process，则 metadata_filter = {{"document_type": "理赔"}}
- 若 intent = product_comparison，则 metadata_filter = {{"document_type": "说明书"}}
- 若 intent = general，则 metadata_filter = null（不使用过滤）。

输出格式要求（关键）：
- 严格按照以下 JSON Schema 输出，仅返回一个 JSON 对象（不要多余文本、不要代码块）。
- 字段键名与类型必须与 Schema 完全一致。
Schema: {schema_json}

用户查询：{query}
"""


STRICT_INTENT_PROMPT_TEMPLATE = """
严格输出一个 JSON 对象，满足 QueryIntent Schema。
禁止输出除 JSON 以外的任何字符；不要使用 Markdown 代码围栏。
Schema: {schema_json}

用户查询：{query}
"""


class QueryIntentService:
    """意图分类服务：调用 LLM 生成 QueryIntent。"""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm = llm_service or LLMService()

    @staticmethod
    def _clean_to_json_str(s: str) -> str:
        s = (s or "").strip()
        # 去除可能的代码围栏
        s = re.sub(r"^```(?:json)?\n|\n```$", "", s).strip()
        # 提取最外层 JSON 对象
        l = s.find("{")
        r = s.rfind("}")
        if l != -1 and r != -1 and r > l:
            return s[l : r + 1]
        return s

    async def classify_intent(self, query: str) -> QueryIntent:
        """
        调用 LLM 分类意图，返回 Pydantic 验证后的 QueryIntent。
        若解析失败，进行一次更严格的重试；最终回退到 general。 
        """
        import json as _json

        schema_json = _json.dumps(QueryIntent.model_json_schema(), ensure_ascii=False)
        messages = [
            {"role": "system", "content": INTENT_PROMPT_TEMPLATE.format(schema_json=schema_json, query=query)},
            {"role": "user", "content": "仅输出一个满足 Schema 的 JSON 对象。"},
        ]

        try:
            resp = await self.llm.agenerate_structured_decision(messages, temperature=0.0, max_tokens=256)
            content = resp.choices[0].message.content if resp and resp.choices else ""
            content = self._clean_to_json_str(content)
            return QueryIntent.model_validate_json(content)
        except ValidationError as ve:
            logger.warning(f"意图分类 JSON 校验失败，进行严格重试：{ve}")
            try:
                strict_messages = [
                    {
                        "role": "system",
                        "content": STRICT_INTENT_PROMPT_TEMPLATE.format(schema_json=schema_json, query=query),
                    },
                    {"role": "user", "content": "仅输出 JSON 对象。"},
                ]
                resp2 = await self.llm.agenerate_structured_decision(strict_messages, temperature=0.0, max_tokens=256)
                content2 = resp2.choices[0].message.content if resp2 and resp2.choices else ""
                content2 = self._clean_to_json_str(content2)
                return QueryIntent.model_validate_json(content2)
            except Exception as e2:
                logger.warning(f"严格重试仍失败，回退到 general：{e2}")
                return QueryIntent(intent="general", metadata_filter=None, reasoning="fallback: parse_failed")
        except Exception as e:
            logger.warning(f"意图分类失败，回退到 general：{e}")
            return QueryIntent(intent="general", metadata_filter=None, reasoning="fallback: llm_failed")
