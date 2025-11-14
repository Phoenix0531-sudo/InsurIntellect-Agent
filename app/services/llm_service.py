"""
大语言模型服务
负责与LLM的交互和问答生成
"""

from typing import List, Dict, Any, Optional, AsyncIterator
from openai import AsyncOpenAI
import time
import asyncio
from app.core.config import settings
from app.core.app_logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """大语言模型服务：与LLM交互并生成问答"""

    def __init__(self, *, model_name: Optional[str] = None, max_tokens: Optional[int] = None, temperature: Optional[float] = None):
        # 初始化 OpenAI 客户端，配置超时（重试由本类统一管理）
        # 兼容硅基流动：允许从 OPENAI_API_KEY/SILICONFLOW_API_KEY 与 OPENAI_BASE_URL/SILICONFLOW_BASE_URL 回退
        api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
        base_url = settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=float(settings.OPENAI_TIMEOUT_SECS),
            max_retries=0,
        )

        # 允许构造时覆盖模型与采样参数（用于轻量/核心分工）
        self.model = (model_name or settings.OPENAI_MODEL)
        self.max_tokens = (max_tokens if max_tokens is not None else settings.OPENAI_MAX_TOKENS)
        self.temperature = (temperature if temperature is not None else settings.OPENAI_TEMPERATURE)

        # 分层模型：核心（重量）与轻量模型名称
        try:
            self.core_model_name = getattr(settings, "OPENAI_MODEL_CORE", None) or self.model
        except Exception:
            self.core_model_name = self.model
        try:
            self.light_model_name = getattr(settings, "OPENAI_MODEL_LIGHT", None) or self.model
        except Exception:
            self.light_model_name = self.model

        # 并发限制（全局 Semaphore，跨实例共享，确保总并发受控）
        if not hasattr(LLMService, "_global_semaphore") or LLMService._global_semaphore is None:
            LLMService._global_semaphore = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
        self.semaphore = LLMService._global_semaphore
        # 熔断状态（类级别共享）
        if not hasattr(LLMService, "_failure_count"):
            LLMService._failure_count = 0
        if not hasattr(LLMService, "_circuit_opened_at"):
            LLMService._circuit_opened_at = None

    @classmethod
    def with_model(cls, model_name: str, *, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> "LLMService":
        """工厂方法：按需指定模型/参数创建实例。"""
        return cls(model_name=model_name, max_tokens=max_tokens, temperature=temperature)

    # --- 可靠性：熔断与退避重试 ---
    def _is_circuit_open(self) -> bool:
        opened_at = getattr(LLMService, "_circuit_opened_at", None)
        if opened_at is None:
            return False
        elapsed = time.time() - opened_at
        if elapsed >= settings.LLM_CIRCUIT_RESET_TIMEOUT:
            # 熔断自动恢复
            LLMService._circuit_opened_at = None
            LLMService._failure_count = 0
            return False
        return True

    def _record_success(self) -> None:
        LLMService._failure_count = 0
        LLMService._circuit_opened_at = None

    def _record_failure(self) -> None:
        LLMService._failure_count += 1
        if LLMService._failure_count >= settings.LLM_CIRCUIT_FAILURE_THRESHOLD:
            if LLMService._circuit_opened_at is None:
                LLMService._circuit_opened_at = time.time()
                logger.warning(
                    f"LLM 熔断开启（失败次数 {LLMService._failure_count}）— 冷却 {settings.LLM_CIRCUIT_RESET_TIMEOUT}s"
                )

    def _backoff_seconds(self, attempt_index: int) -> float:
        base = settings.LLM_BACKOFF_BASE
        factor = settings.LLM_BACKOFF_FACTOR
        max_v = settings.LLM_BACKOFF_MAX
        delay = base * (factor ** attempt_index)
        return min(delay, max_v)

    async def _chat_completion(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """统一封装：并发限制 + 熔断 + 退避重试。"""
        if self._is_circuit_open():
            raise RuntimeError("LLM 熔断中，请稍后重试")

        # 并发控制：等待不超过回答超时阈值，避免请求在队列中耗尽客户端超时
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=getattr(settings, "LLM_QUEUE_TIMEOUT_SECS", 0.75))
        except asyncio.TimeoutError:
            raise TimeoutError("LLM 并发队列等待超时")
        try:
            last_err: Optional[Exception] = None
            max_attempts = max(1, settings.LLM_MAX_RETRIES)
            for attempt in range(max_attempts):
                try:
                    resp = await self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        **kwargs,
                    )
                    self._record_success()
                    return resp
                except Exception as e:
                    last_err = e
                    self._record_failure()
                    # 最后一次失败直接抛出
                    if attempt >= max_attempts - 1:
                        break
                    delay = self._backoff_seconds(attempt)
                    logger.warning(f"LLM 调用失败（第 {attempt+1} 次），退避 {delay:.2f}s：{e}")
                    await asyncio.sleep(delay)
            # 如果失败并且达到阈值，可能开启熔断
            if last_err is not None:
                raise last_err
        finally:
            self.semaphore.release()

    async def _chat_completion_stream(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """流式封装：并发限制 + 熔断 + 退避重试。

        返回异步流对象（Async Stream），调用方可 async for 进行增量消费。
        """
        if self._is_circuit_open():
            raise RuntimeError("LLM 熔断中，请稍后重试")

        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=getattr(settings, "LLM_QUEUE_TIMEOUT_SECS", 0.75))
        except asyncio.TimeoutError:
            raise TimeoutError("LLM 并发队列等待超时(流式)")
        try:
            last_err: Optional[Exception] = None
            max_attempts = max(1, settings.LLM_MAX_RETRIES)
            for attempt in range(max_attempts):
                try:
                    stream = await self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        **kwargs,
                    )
                    self._record_success()
                    return stream
                except Exception as e:
                    last_err = e
                    self._record_failure()
                    if attempt >= max_attempts - 1:
                        break
                    delay = self._backoff_seconds(attempt)
                    logger.warning(f"LLM 流式调用失败（第 {attempt+1} 次），退避 {delay:.2f}s：{e}")
                    await asyncio.sleep(delay)
            if last_err is not None:
                raise last_err
        finally:
            self.semaphore.release()

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
        """构建用户提示词（支持知识图谱事实优先展示）。"""
        kg_parts: List[str] = []
        doc_parts: List[str] = []

        for i, chunk in enumerate(context_chunks, 1):
            content = chunk.get("content", "")
            page_num = chunk.get("page_number", "N/A")
            doc_name = chunk.get("document_name", "Unknown")
            meta = chunk.get("metadata", {})
            is_kg = False
            try:
                if isinstance(meta, dict):
                    is_kg = bool(meta.get("is_kg"))
            except Exception:
                is_kg = False

            if is_kg:
                kg_parts.append(content)
            else:
                doc_parts.append(
                    f"文档片段 {i}:\n来源: {doc_name} (第{page_num}页)\n内容: {content}\n"
                )

        sections: List[str] = []
        if kg_parts:
            sections.append("知识图谱事实:\n" + "\n".join(kg_parts))
        if doc_parts:
            sections.append("文档片段:\n" + "\n".join(doc_parts))

        context = "\n\n".join(sections) if sections else "(无上下文)"

        prompt = (
            "基于以下保险文档内容和知识图谱事实，请回答用户的问题：\n\n"
            f"{context}\n\n"
            f"用户问题：{query}\n\n"
            "请基于上述内容回答问题。如果没有相关信息，请明确说明："
            "'根据提供的文档内容和事实，我无法找到相关信息来回答这个问题'。"
        )
        return prompt

    async def agenerate_response(self, query: str, context_chunks: List[Dict[str, Any]], *, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """非流式：生成完整回复（满足 T2.3/T2.4）。"""
        start_time = time.time()

        try:
            if self._is_circuit_open():
                raise RuntimeError("LLM 熔断中，请稍后重试")

            messages = [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_prompt(query, context_chunks)},
            ]

            try:
                await asyncio.wait_for(self.semaphore.acquire(), timeout=getattr(settings, "LLM_QUEUE_TIMEOUT_SECS", 0.75))
            except asyncio.TimeoutError:
                raise TimeoutError("LLM 并发队列等待超时")
            try:
                last_err: Optional[Exception] = None
                max_attempts = max(1, settings.LLM_MAX_RETRIES)
                response = None
                for attempt in range(max_attempts):
                    try:
                        response = await self.client.chat.completions.create(
                            model=self.core_model_name,
                            messages=messages,
                            max_tokens=(max_tokens or self.max_tokens),
                            temperature=(temperature if temperature is not None else self.temperature),
                            stream=False,
                        )
                        self._record_success()
                        break
                    except Exception as e:
                        last_err = e
                        self._record_failure()
                        if attempt >= max_attempts - 1:
                            break
                        delay = self._backoff_seconds(attempt)
                        logger.warning(f"LLM 调用失败（第 {attempt+1} 次），退避 {delay:.2f}s：{e}")
                        await asyncio.sleep(delay)
                if response is None and last_err is not None:
                    raise last_err
            finally:
                self.semaphore.release()

            answer = response.choices[0].message.content.strip()
            tokens_used = getattr(response.usage, "total_tokens", 0)
            response_time = time.time() - start_time

            return {
                "answer": answer,
                "model_used": self.core_model_name,
                "tokens_used": tokens_used,
                "response_time": response_time,
                "success": True,
            }

        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"LLM回复生成失败: {e}")
            return {
                "answer": "抱歉, 生成回复时出现错误, 请稍后重试。",
                "model_used": self.core_model_name,
                "tokens_used": 0,
                "response_time": response_time,
                "success": False,
                "error": str(e),
            }

    async def agenerate_stream(self, query: str, context_chunks: List[Dict[str, Any]], *, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> AsyncIterator[str]:
        """流式：异步生成器，逐个 yield 文本增量（满足 T2.5/T2.6）。"""
        if self._is_circuit_open():
            # 将熔断暴露给上层，便于 SSE 报错
            raise RuntimeError("LLM 熔断中，请稍后重试")

        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": self._build_user_prompt(query, context_chunks)},
        ]

        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=getattr(settings, "LLM_QUEUE_TIMEOUT_SECS", 0.75))
        except asyncio.TimeoutError:
            raise TimeoutError("LLM 并发队列等待超时(流式)")
        try:
            last_err: Optional[Exception] = None
            max_attempts = max(1, settings.LLM_MAX_RETRIES)
            stream = None
            for attempt in range(max_attempts):
                try:
                    stream = await self.client.chat.completions.create(
                        model=self.core_model_name,
                        messages=messages,
                        stream=True,
                        max_tokens=(max_tokens or self.max_tokens),
                        temperature=(temperature if temperature is not None else self.temperature),
                    )
                    self._record_success()
                    break
                except Exception as e:
                    last_err = e
                    self._record_failure()
                    if attempt >= max_attempts - 1:
                        break
                    delay = self._backoff_seconds(attempt)
                    logger.warning(f"LLM 流式调用失败（第 {attempt+1} 次），退避 {delay:.2f}s：{e}")
                    await asyncio.sleep(delay)
            if stream is None and last_err is not None:
                raise last_err
        finally:
            self.semaphore.release()

        async for event in stream:
            try:
                if hasattr(event, "choices") and event.choices:
                    delta = event.choices[0].delta
                    content_delta = getattr(delta, "content", None)
                    if content_delta:
                        yield content_delta
            except Exception:
                # 忽略单次解析异常，继续流
                pass

    async def agenerate_structured_decision(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> Any:
        """
        轻量任务：路由/意图/重写 等结构化决策调用，强制使用 light 模型。
        返回 OpenAI ChatCompletion 响应对象，由调用方自行解析 JSON。
        """
        if self._is_circuit_open():
            raise RuntimeError("LLM 熔断中，请稍后重试")

        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=getattr(settings, "LLM_QUEUE_TIMEOUT_SECS", 0.75))
        except asyncio.TimeoutError:
            raise TimeoutError("LLM 并发队列等待超时")

        try:
            last_err: Optional[Exception] = None
            max_attempts = max(1, settings.LLM_MAX_RETRIES)
            for attempt in range(max_attempts):
                try:
                    resp = await self.client.chat.completions.create(
                        model=self.light_model_name,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    self._record_success()
                    return resp
                except Exception as e:
                    last_err = e
                    self._record_failure()
                    if attempt >= max_attempts - 1:
                        break
                    delay = self._backoff_seconds(attempt)
                    logger.warning(f"LLM 轻量决策失败（第 {attempt+1} 次），退避 {delay:.2f}s：{e}")
                    await asyncio.sleep(delay)
            if last_err is not None:
                raise last_err
        finally:
            self.semaphore.release()

    async def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成问答回复"""
        start_time = time.time()

        try:
            messages = [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_prompt(query, context_chunks)},
            ]

            response = await self._chat_completion(
                messages,
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

    async def stream_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
        """以流式方式生成问答回复。

        事件流结构：
        - {"type": "start", "model_used": ..., "timestamp": ...}
        - {"type": "token", "content": "..."}  // 多次
        - {"type": "end", "answer": "...", "tokens_used": N, "response_time": S, "success": True}
        - 若失败：{"type": "error", "message": "...", "response_time": S}
        """
        started_at = time.time()
        # 构建消息
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": self._build_user_prompt(query, context_chunks)},
        ]

        # 起始事件
        yield {
            "type": "start",
            "model_used": self.model,
            "timestamp": started_at,
        }

        final_text: str = ""
        try:
            stream = await self._chat_completion_stream(
                messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            async for event in stream:
                try:
                    # OpenAI v1: ChatCompletionChunk -> choices[0].delta.content
                    if hasattr(event, "choices") and event.choices:
                        delta = event.choices[0].delta
                        content_delta = getattr(delta, "content", None)
                        if content_delta:
                            final_text += content_delta
                            yield {"type": "token", "content": content_delta}
                except Exception as parse_err:
                    # 忽略解析异常，继续流（不终止）
                    logger.debug(f"流事件解析异常: {parse_err}")

            # 结束后尝试获取最终响应以读取用量
            tokens_used = 0
            try:
                final_resp = await stream.get_final_response()
                tokens_used = getattr(getattr(final_resp, "usage", None), "total_tokens", 0) or 0
            except Exception:
                tokens_used = 0

            response_time = time.time() - started_at
            yield {
                "type": "end",
                "answer": final_text.strip(),
                "model_used": self.model,
                "tokens_used": tokens_used,
                "response_time": response_time,
                "success": True,
            }

        except Exception as e:
            response_time = time.time() - started_at
            logger.error(f"LLM流式生成失败: {e}")
            yield {
                "type": "error",
                "message": str(e),
                "model_used": self.model,
                "response_time": response_time,
                "success": False,
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

            response = await self._chat_completion(
                messages,
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

            response = await self._chat_completion(
                messages,
                max_tokens=100,
                temperature=0.3,
            )

            keywords_text = response.choices[0].message.content.strip()
            keywords = [kw.strip() for kw in keywords_text.split(",")]

            logger.info(f"关键词提取成功, 共 {len(keywords)} 个")
            return keywords[:max_keywords]

        except Exception as e:
            # 回退到本地关键词提取（jieba.analyse）以避免429等限流问题
            try:
                import jieba.analyse as analyse  # type: ignore
                kws = analyse.extract_tags(text or "", topK=max_keywords)
                logger.info(f"关键词本地回退成功, 共 {len(kws)} 个")
                return kws
            except Exception as e2:
                logger.warning(f"关键词提取失败且本地回退异常: {e} / {e2}")
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

            response = await self._chat_completion(
                messages,
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
            await self._chat_completion(
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

            response = await self._chat_completion(
                messages,
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

