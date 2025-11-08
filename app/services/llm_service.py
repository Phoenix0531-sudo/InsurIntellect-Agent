"""
大语言模型服务
负责与LLM的交互和问答生成
"""

from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
import time
from app.core.config import settings
from app.core.app_logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """大语言模型服务：与LLM交互并生成问答"""

    def __init__(self):
        # 初始化 OpenAI 客户端，配置超时和重试参数
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=30.0,
            max_retries=2,
        )

        self.model = settings.OPENAI_MODEL
        self.max_tokens = settings.OPENAI_MAX_TOKENS
        self.temperature = settings.OPENAI_TEMPERATURE

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return (
            "你是一个专业的保险文档问答助手。"
            "你的任务是基于提供的保险文档内容，准确、专业地回答用户的问题。\n"
            "请遵循以下原则：\n"
            "1. 仅基于提供的文档内容回答问题，不要编造信息\n"
            "2. 如果文档中没有相关信息，请明确说明\n"
            "3. 回答要准确、简洁、专业\n"
            "4. 如果涉及具体的保险条款或数字，请直接引用原文\n"
            "5. 保持客观中立的语调\n"
            "6. 如果问题不清楚，可以要求用户澄清\n"
            "请用中文回答问题。"
        )

    def _build_user_prompt(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """构建用户提示词"""
        context_parts: List[str] = []
        for i, chunk in enumerate(context_chunks, 1):
            content = chunk.get("content", "")
            page_num = chunk.get("page_number", "N/A")
            doc_name = chunk.get("document_name", "Unknown")

            context_parts.append(
                f"文档片段 {i}:\n来源: {doc_name} (第{page_num}页)\n内容: {content}\n"
            )

        context = "\n".join(context_parts)

        prompt = (
            "基于以下保险文档内容，请回答用户的问题：\n\n"
            f"{context}\n\n"
            f"用户问题：{query}\n\n"
            "请基于上述文档内容回答问题。如果文档中没有相关信息，请说明 "
            "'根据提供的文档内容，我无法找到相关信息来回答这个问题'。"
        )
        return prompt

    async def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成问答回复"""
        start_time = time.time()

        try:
            messages = [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_prompt(query, context_chunks)},
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=False,
            )

            answer = response.choices[0].message.content.strip()
            tokens_used = getattr(response.usage, "total_tokens", 0)
            response_time = time.time() - start_time

            result = {
                "answer": answer,
                "model_used": self.model,
                "tokens_used": tokens_used,
                "response_time": response_time,
                "success": True,
            }

            logger.info(
                f"LLM回复生成成功, 用时 {response_time:.2f}s, 使用 {tokens_used} tokens"
            )
            return result

        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"LLM回复生成失败: {e}")

            return {
                "answer": "抱歉, 生成回复时出现错误, 请稍后重试。",
                "model_used": self.model,
                "tokens_used": 0,
                "response_time": response_time,
                "success": False,
                "error": str(e),
            }

    async def generate_summary(self, text: str, max_length: int = 200) -> str:
        """生成文本摘要"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": f"请为以下文本生成一个简洁的摘要, 长度不超过 {max_length} 个字符。",
                },
                {"role": "user", "content": text},
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_length // 2,
                temperature=0.3,
            )

            summary = response.choices[0].message.content.strip()
            logger.info("文本摘要生成成功")
            return summary

        except Exception as e:
            logger.error(f"文本摘要生成失败: {e}")
            return text[:max_length] + "..." if len(text) > max_length else text

    async def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"请从以下文本中提取最重要的 {max_keywords} 个关键词, 用逗号分隔。"
                    ),
                },
                {"role": "user", "content": text},
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=100,
                temperature=0.3,
            )

            keywords_text = response.choices[0].message.content.strip()
            keywords = [kw.strip() for kw in keywords_text.split(",")]

            logger.info(f"关键词提取成功, 共 {len(keywords)} 个")
            return keywords[:max_keywords]

        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return []

    async def classify_query(self, query: str) -> Dict[str, Any]:
        """查询分类"""
        try:
            categories = [
                "保险条款查询",
                "理赔相关",
                "保费计算",
                "保险产品对比",
                "投保流程",
                "其他",
            ]

            messages = [
                {
                    "role": "system",
                    "content": (
                        f"请将以下查询分类到这些类别中的一个: {', '.join(categories)}。只返回类别名称。"
                    ),
                },
                {"role": "user", "content": query},
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=50,
                temperature=0.1,
            )

            category = response.choices[0].message.content.strip()
            if category not in categories:
                category = "其他"

            logger.info(f"查询分类完成: {category}")
            return {"category": category, "confidence": 0.8, "success": True}

        except Exception as e:
            logger.error(f"查询分类失败: {e}")
            return {
                "category": "其他",
                "confidence": 0.0,
                "success": False,
                "error": str(e),
            }

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
                temperature=0,
            )
            return True

        except Exception as e:
            logger.error(f"LLM 服务健康检查失败: {e}")
            return False

    async def rewrite_query(
        self,
        user_query: str,
        ontology: Dict[str, Any],
        max_output_tokens: int = 256,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """口语化查询重写：将用户原始问题转换为专业的、语义更丰富的检索查询。

        输入：用户原始查询与保险术语本体库（JSON结构）
        输出：字典，包含 rewritten_query、intent_tags、keywords、constraints 等字段
        失败时返回 success=False 并提供错误信息。
        """
        try:
            # 将本体库压缩为有限长度的字符串，避免超长提示
            import json as _json
            ontology_text = _json.dumps(ontology, ensure_ascii=False)
            if len(ontology_text) > 4000:
                ontology_text = ontology_text[:4000] + "..."

            system_prompt = (
                "你是保险查询重写专家。你的任务：基于保险术语本体库，将用户口语化问题重写为专业、语义丰富的检索查询。"
                "要求：\n"
                "- 使用术语同义词与标准化名称（本体库提供）\n"
                "- 明确产品类型、保障责任、限制条件与关键数字\n"
                "- 保持中文，避免增加未给出的新事实\n"
                "- 输出JSON结构，字段：rewritten_query、intent_tags、keywords、constraints\n"
            )

            user_content = (
                f"保险术语本体库（片段）：\n{ontology_text}\n\n"
                f"用户原始问题：\n{user_query}\n\n"
                "请重写为用于向量检索的专业查询，并返回如下JSON：\n"
                "{\n"
                "  \"rewritten_query\": \"...\",\n"
                "  \"intent_tags\": [\"产品类型\", \"保障责任\", \"条款/限制\"],\n"
                "  \"keywords\": [\"标准术语或关键短语\"],\n"
                "  \"constraints\": {\"等待期\": \"30天\", \"免赔额\": \"1000元\"}\n"
                "}"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_output_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content.strip()
            # 尝试抽取JSON
            import json as _json2
            parsed: Optional[Dict[str, Any]] = None
            try:
                if "```json" in content:
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    if end != -1:
                        content = content[start:end].strip()
                elif content.startswith("{"):
                    pass
                parsed = _json2.loads(content)
            except Exception:
                # 尝试第二种方式：提取第一段以 { 开头的块
                l = content.find("{")
                r = content.rfind("}")
                if l != -1 and r != -1 and r > l:
                    try:
                        parsed = _json2.loads(content[l : r + 1])
                    except Exception:
                        parsed = None

            if not isinstance(parsed, dict):
                logger.warning("重写结果解析失败，回退到原始查询")
                return {
                    "rewritten_query": user_query,
                    "intent_tags": [],
                    "keywords": [],
                    "constraints": {},
                    "success": False,
                    "error": "解析失败",
                }

            rewritten = parsed.get("rewritten_query") or user_query
            return {
                "rewritten_query": rewritten,
                "intent_tags": parsed.get("intent_tags", []),
                "keywords": parsed.get("keywords", []),
                "constraints": parsed.get("constraints", {}),
                "success": True,
            }

        except Exception as e:
            logger.error(f"查询重写失败: {e}")
            return {
                "rewritten_query": user_query,
                "intent_tags": [],
                "keywords": [],
                "constraints": {},
                "success": False,
                "error": str(e),
            }

