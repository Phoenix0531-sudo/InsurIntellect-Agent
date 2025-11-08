"""
查询服务
整合向量搜索和LLM生成,提供完整的问答功能
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
import json
from functools import lru_cache
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.app_logging import get_logger
from app.models.database_models import QueryHistory, Document, DocumentChunk
from app.models.schemas import QueryRequest, QueryResponse, RetrievedChunk, QueryStatistics
from app.core.rag_workflow import get_agent
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class QueryService:
    """查询服务"""
    
    def __init__(self):
        """初始化查询服务,使用InsurIntellectAgent RAG工作流"""
        # 延迟初始化agent,避免在服务启动时就创建
        self._agent = None
    
    @property
    def agent(self):
        """获取agent实例,使用延迟初始化"""
        if self._agent is None:
            logger.info("初始化agent实例...")
            try:
                self._agent = get_agent()
                logger.info(f"Agent实例初始化成功: {type(self._agent)}")
            except Exception as e:
                logger.error(f"Agent实例初始化失败: {e}", exc_info=True)
                raise
        return self._agent
    
    async def process_query(
        self, 
        db: Session, 
        request: QueryRequest
    ) -> QueryResponse:
        """处理查询请求,使用InsurIntellectAgent RAG工作流"""
        start_time = datetime.utcnow()
        
        try:
            # 使用InsurIntellectAgent处理查询
            logger.debug(f"QueryService.process_query 开始处理查询: {request.question}")

            logger.debug("获取agent实例...")
            agent = self.agent
            logger.debug(f"Agent实例类型: {type(agent)}")
            # 在向量检索前进行查询重写（攻关任务二）
            question_for_retrieval = request.question
            rewrite_result: Dict[str, Any] = {}
            if settings.ENABLE_QUERY_REWRITING:
                try:
                    logger.info("启用查询重写引擎，准备重写用户问题")
                    llm = LLMService()
                    ontology = _load_ontology()
                    rewrite_result = await llm.rewrite_query(user_query=request.question, ontology=ontology)
                    if rewrite_result.get("success") and rewrite_result.get("rewritten_query"):
                        question_for_retrieval = rewrite_result["rewritten_query"]
                        logger.info(f"查询已重写：{question_for_retrieval}")
                    else:
                        logger.warning("查询重写失败或不可用，回退到原始查询")
                except Exception as e:
                    logger.error(f"查询重写过程异常，回退到原始查询: {e}")

            logger.debug("调用agent.answer方法...")
            answer = agent.answer(question_for_retrieval)
            logger.debug(f"Agent返回答案: {answer[:100]}..." if len(answer) > 100 else f"Agent返回答案: {answer}")

            # 从 agent 收集检索与排序审计信息（用于响应与持久化）
            retrieved_chunks = []
            try:
                if getattr(agent, "last_run", None) and agent.last_run.get("retrieved_chunks"):
                    retrieved_chunks = agent.last_run.get("retrieved_chunks", [])
            except Exception as _:
                retrieved_chunks = []
            
            # 计算响应时间
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.debug("构建响应对象...")
            # 构建响应
            response = QueryResponse(
                question=request.question,
                answer=answer,
                query_type=request.query_type,
                response_time=response_time,
                chunks_used=request.max_chunks,  # 实际使用的chunk数量由agent内部决定
                retrieved_chunks=[RetrievedChunk(**c) for c in retrieved_chunks] if retrieved_chunks else [],
                confidence_score=0.9,  # 默认置信度,可以后续优化
                query_id=None  # 将在保存历史记录后设置
            )
            logger.debug("响应对象构建成功")
            
            logger.debug("保存查询历史...")
            # 保存查询历史
            try:
                rewriting_metadata_json = None
                if rewrite_result:
                    try:
                        rewriting_metadata_json = json.dumps({
                            "intent_tags": rewrite_result.get("intent_tags"),
                            "keywords": rewrite_result.get("keywords"),
                            "constraints": rewrite_result.get("constraints"),
                        }, ensure_ascii=False)
                    except Exception as _:
                        rewriting_metadata_json = None

                query_id = await self._save_query_history(
                    db, 
                    request.question, 
                    answer, 
                    request.query_type, 
                    response_time, 
                    request.max_chunks,
                    rewritten_query=question_for_retrieval if question_for_retrieval != request.question else None,
                    rewriting_metadata_json=rewriting_metadata_json,
                    retrieved_chunks_json=json.dumps(retrieved_chunks, ensure_ascii=False) if retrieved_chunks else None
                )
                response.query_id = query_id
                logger.debug(f"查询历史保存成功,ID: {query_id}")
            except Exception as save_error:
                logger.warning(f"查询历史保存失败: {save_error}")
                # 继续返回响应,不因为历史保存失败而中断
            
            logger.debug("查询处理完全成功")
            logger.info(f"查询处理完成: {request.question[:50]}..., 用时 {response_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"查询处理异常: {e}")
            logger.error(f"异常类型: {type(e).__name__}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            
            logger.error(f"查询处理失败: {e}", exc_info=True)
            logger.error(f"异常类型: {type(e).__name__}")
            logger.error(f"异常详情: {str(e)}")
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            error_response = QueryResponse(
                question=request.question,
                answer="抱歉,处理您的查询时出现了错误,请稍后重试",
                query_type=request.query_type,
                response_time=response_time,
                chunks_used=0,
                retrieved_chunks=[],
                confidence_score=0.0,
                query_id=None
            )
            # 即使出现异常，也尝试保存查询历史，确保返回 query_id
            try:
                query_id = await self._save_query_history(
                    db,
                    request.question,
                    error_response.answer,
                    request.query_type,
                    response_time,
                    0,
                    rewritten_query=None,
                    rewriting_metadata_json=None,
                    retrieved_chunks_json=None,
                )
                error_response.query_id = query_id
                logger.debug(f"错误响应已保存历史,ID: {query_id}")
            except Exception as save_error:
                logger.warning(f"错误响应保存历史失败: {save_error}")
            
            logger.debug("返回错误响应")
            return error_response

    async def _save_query_history(
        self, 
        db: Session, 
        question: str, 
        answer: str, 
        query_type: str, 
        response_time: float, 
        chunks_used: int,
        rewritten_query: Optional[str] = None,
        rewriting_metadata_json: Optional[str] = None,
        retrieved_chunks_json: Optional[str] = None
    ) -> Optional[int]:
        """保存查询历史"""
        try:
            # 确保数据库存在重写相关列（无迁移环境下的轻量DDL）
            try:
                inspector = inspect(db.bind)
                cols = {c['name'] for c in inspector.get_columns('query_history')}
                if 'rewritten_query' not in cols:
                    db.execute(text("ALTER TABLE query_history ADD COLUMN rewritten_query TEXT"))
                if 'rewriting_metadata_json' not in cols:
                    db.execute(text("ALTER TABLE query_history ADD COLUMN rewriting_metadata_json TEXT"))
                if 'retrieved_chunks' not in cols:
                    db.execute(text("ALTER TABLE query_history ADD COLUMN retrieved_chunks TEXT"))
                db.commit()
            except Exception:
                # 若检查或DDL失败，不影响后续保存（可能是首次建表或权限限制）
                db.rollback()

            # 创建查询历史记录
            query_history = QueryHistory(
                query=question,
                response=answer,
                model_used=query_type,
                response_time=response_time,
                retrieved_chunks=retrieved_chunks_json,
                tokens_used=None,
                cost=None,
                rating=None,
                feedback=None,
                rewritten_query=rewritten_query,
                rewriting_metadata_json=rewriting_metadata_json
            )
            
            db.add(query_history)
            db.commit()
            db.refresh(query_history)
            
            logger.info(f"查询历史保存成功,ID: {query_history.id}")
            return query_history.id
            
        except Exception as e:
            logger.error(f"保存查询历史失败: {e}")
            db.rollback()
            return None

    async def get_query_history(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 50,
        query_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[QueryHistory]:
        """获取查询历史"""
        try:
            query = db.query(QueryHistory)

            # 数据库模型使用 model_used 作为查询类型字段
            if query_type:
                query = query.filter(QueryHistory.model_used == query_type)

            # 统一使用 created_time 字段进行时间过滤
            if start_date:
                query = query.filter(QueryHistory.created_time >= start_date)

            if end_date:
                query = query.filter(QueryHistory.created_time <= end_date)

            history = query.order_by(QueryHistory.created_time.desc()).offset(skip).limit(limit).all()

            logger.info(f"获取查询历史成功,共 {len(history)} 条记录")
            return history

        except Exception as e:
            logger.error(f"获取查询历史失败: {e}")
            return []

    async def update_query_feedback(
        self,
        db: Session,
        query_id: int,
        rating: int,
        comment: Optional[str] = None
    ) -> bool:
        """更新查询反馈"""
        try:
            query_history = db.query(QueryHistory).filter(QueryHistory.id == query_id).first()

            if not query_history:
                logger.warning(f"查询记录不存在: {query_id}")
                return False

            # 与数据库模型字段对齐
            query_history.rating = rating
            query_history.feedback = comment
            db.commit()

            logger.info(f"查询反馈更新成功: query_id={query_id}, rating={rating}")
            return True

        except Exception as e:
            logger.error(f"更新查询反馈失败: {e}")
            db.rollback()
            return False

    async def get_query_statistics(self, db: Session, days: int = 30) -> QueryStatistics:
        """获取查询统计信息"""
        try:
            from sqlalchemy import func
            from datetime import timedelta

            # 计算时间范围
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # 总查询数
            total_queries = db.query(QueryHistory).filter(
                QueryHistory.created_time >= start_date
            ).count()

            # 平均响应时间
            avg_response_time = db.query(func.avg(QueryHistory.response_time)).filter(
                QueryHistory.created_time >= start_date
            ).scalar() or 0

            # 平均评分
            avg_rating = db.query(func.avg(QueryHistory.rating)).filter(
                QueryHistory.rating.isnot(None),
                QueryHistory.created_time >= start_date
            ).scalar() or 0

            # 今日查询数
            today = datetime.utcnow().date()
            today_queries = db.query(QueryHistory).filter(
                func.date(QueryHistory.created_time) == today
            ).count()

            # 查询类型分布 - 由于数据库模型中没有query_type字段,使用model_used代替
            query_type_stats = db.query(
                QueryHistory.model_used,
                func.count(QueryHistory.model_used).label('count')
            ).filter(
                QueryHistory.created_time >= start_date
            ).group_by(QueryHistory.model_used).all()

            query_type_distribution = {stat[0]: stat[1] for stat in query_type_stats}

            stats = QueryStatistics(
                total_queries=total_queries,
                avg_response_time=round(avg_response_time, 3),
                avg_rating=round(avg_rating, 2),
                today_queries=today_queries,
                query_type_distribution=query_type_distribution,
                period_days=days,
                avg_chunks_used=0.0,  # 添加缺失字段
                avg_confidence_score=0.0,  # 添加缺失字段
                feedback_stats={}  # 添加缺失字段
            )

            logger.info("查询统计信息获取成功")
            return stats

        except Exception as e:
            logger.error(f"获取查询统计信息失败: {e}")
            return QueryStatistics(
                total_queries=0,
                avg_response_time=0,
                avg_rating=0,
                today_queries=0,
                query_type_distribution={},
                period_days=days,
                avg_chunks_used=0.0,  # 添加缺失字段
                avg_confidence_score=0.0,  # 添加缺失字段
                feedback_stats={}  # 添加缺失字段
            )


@lru_cache(maxsize=1)
def _load_ontology() -> dict:
    """加载保险术语本体库JSON，使用缓存减少I/O。"""
    try:
        with open(settings.ONTOLOGY_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载本体库失败，使用空本体：{e}")
        return {
            "synonyms": {},
            "product_types": [],
            "coverage_terms": [],
            "claim_terms": [],
            "exclusions": [],
        }


