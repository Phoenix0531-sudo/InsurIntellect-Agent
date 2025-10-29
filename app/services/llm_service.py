"""
大语言模型服务
负责与LLM的交互和问答生成
"""

from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
import time
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """大语言模型服务类"""
    
    def __init__(self):
        # 初始化OpenAI客户端，配置超时和重试参数
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=30.0,  # 30秒超时
            max_retries=2  # 最多重试2次
        )
        
        self.model = settings.OPENAI_MODEL
        self.max_tokens = settings.OPENAI_MAX_TOKENS
        self.temperature = settings.OPENAI_TEMPERATURE
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是一个专业的保险文档问答助手。你的任务是基于提供的保险文档内容，准确、专业地回答用户的问题。

请遵循以下原则：
1. 仅基于提供的文档内容回答问题，不要编造信息
2. 如果文档中没有相关信息，请明确说明
3. 回答要准确、简洁、专业
4. 如果涉及具体的保险条款或数字，请直接引用原文
5. 保持客观中立的语调
6. 如果问题不清楚，可以要求用户澄清

请用中文回答问题。"""
    
    def _build_user_prompt(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """构建用户提示词"""
        # 构建上下文
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            content = chunk.get('content', '')
            page_num = chunk.get('page_number', 'N/A')
            doc_name = chunk.get('document_name', 'Unknown')
            
            context_parts.append(f"""
文档片段 {i}:
来源: {doc_name} (第{page_num}页)
内容: {content}
""")
        
        context = "\n".join(context_parts)
        
        prompt = f"""
基于以下保险文档内容，请回答用户的问题：

{context}

用户问题: {query}

请基于上述文档内容回答问题。如果文档中没有相关信息，请说明"根据提供的文档内容，我无法找到相关信息来回答这个问题。"
"""
        return prompt
    
    async def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成问答回复"""
        start_time = time.time()
        
        try:
            # 构建消息
            messages = [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_prompt(query, context_chunks)}
            ]
            
            # 调用OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=False
            )
            
            # 提取回复
            answer = response.choices[0].message.content.strip()
            tokens_used = response.usage.total_tokens
            
            response_time = time.time() - start_time
            
            result = {
                "answer": answer,
                "model_used": self.model,
                "tokens_used": tokens_used,
                "response_time": response_time,
                "success": True
            }
            
            logger.info(f"LLM回复生成成功，用时 {response_time:.2f}s，使用 {tokens_used} tokens")
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"LLM回复生成失败: {e}")
            
            return {
                "answer": "抱歉，生成回复时出现错误，请稍后重试。",
                "model_used": self.model,
                "tokens_used": 0,
                "response_time": response_time,
                "success": False,
                "error": str(e)
            }
    
    async def generate_summary(self, text: str, max_length: int = 200) -> str:
        """生成文本摘要"""
        try:
            messages = [
                {
                    "role": "system", 
                    "content": f"请为以下文本生成一个简洁的摘要，长度不超过{max_length}个字符。"
                },
                {"role": "user", "content": text}
            ]
            
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=messages,
                max_tokens=max_length // 2,  # 估算token数
                temperature=0.3
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
                    "content": f"请从以下文本中提取最重要的{max_keywords}个关键词，用逗号分隔。"
                },
                {"role": "user", "content": text}
            ]
            
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=messages,
                max_tokens=100,
                temperature=0.3
            )
            
            keywords_text = response.choices[0].message.content.strip()
            keywords = [kw.strip() for kw in keywords_text.split(',')]
            
            logger.info(f"关键词提取成功，共{len(keywords)}个")
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
                "其他"
            ]
            
            messages = [
                {
                    "role": "system", 
                    "content": f"请将以下查询分类到这些类别中的一个：{', '.join(categories)}。只返回类别名称。"
                },
                {"role": "user", "content": query}
            ]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=50,
                temperature=0.1
            )
            
            category = response.choices[0].message.content.strip()
            
            # 验证分类结果
            if category not in categories:
                category = "其他"
            
            logger.info(f"查询分类完成: {category}")
            return {
                "category": category,
                "confidence": 0.8,  # 简化的置信度
                "success": True
            }
            
        except Exception as e:
            logger.error(f"查询分类失败: {e}")
            return {
                "category": "其他",
                "confidence": 0.0,
                "success": False,
                "error": str(e)
            }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 设置较短的超时时间，避免长时间等待
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
                temperature=0,
                timeout=10.0  # 10秒超时
            )
            return True
            
        except Exception as e:
            logger.error(f"LLM服务健康检查失败: {e}")
            return False