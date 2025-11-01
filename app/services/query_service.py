"""
查询服务
整合向量搜索和LLM生成,提供完整的问答功能
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.app_logging import get_logger
from app.models.database_models import QueryHistory, Document, DocumentChunk
from app.models.schemas import QueryRequest, QueryResponse, RetrievedChunk, QueryStatistics
from app.core.rag_workflow import get_agent

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

            logger.debug("调用agent.answer方法...")
            answer = agent.answer(request.question)
            logger.debug(f"Agent返回答案: {answer[:100]}..." if len(answer) > 100 else f"Agent返回答案: {answer}")
            
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
                retrieved_chunks=[],  # 暂时为空,可以后续扩展
                confidence_score=0.9,  # 默认置信度,可以后续优化
                query_id=None  # 将在保存历史记录后设置
            )
            logger.debug("响应对象构建成功")
            
            logger.debug("保存查询历史...")
            # 保存查询历史
            try:
                query_id = await self._save_query_history(
                    db, 
                    request.question, 
                    answer, 
                    request.query_type, 
                    response_time, 
                    request.max_chunks
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
            
            logger.debug("返回错误响应")
            return error_response
    
    async def _save_query_history(
        self, 
        db: Session, 
        question: str, 
        answer: str, 
        query_type: str, 
        response_time: float, 
        chunks_used: int
    ) -> Optional[int]:
        """保存查询历史"""
        try:
            # 创建查询历史记录
            query_history = QueryHistory(
                query=question,
                response=answer,
                model_used=query_type,
                response_time=response_time,
                retrieved_chunks=None,  # 可以后续扩展
                tokens_used=None,
                cost=None,
                rating=None,
                feedback=None
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
            
            if query_type:
                query = query.filter(QueryHistory.query_type == query_type)
            
            if start_date:
                query = query.filter(QueryHistory.created_at >= start_date)
                
            if end_date:
                query = query.filter(QueryHistory.created_at <= end_date)
            
            history = query.order_by(QueryHistory.created_at.desc()).offset(skip).limit(limit).all()
            
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
            
            query_history.feedback_rating = rating
            query_history.feedback_comment = comment
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


