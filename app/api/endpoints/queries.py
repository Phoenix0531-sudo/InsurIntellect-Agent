"""
查询处理API端点
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.database_models import QueryHistory
from app.models.schemas import (
    QueryRequest, QueryResponse, QueryHistoryResponse, 
    FeedbackRequest, QueryStatistics, ErrorResponse
)
from app.services.query_service import QueryService

logger = get_logger(__name__)
router = APIRouter()


@router.post("/ask", response_model=QueryResponse, summary="提交问题查询")
async def ask_question(
    query_request: QueryRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    提交问题并获取基于文档的回答
    
    支持的查询类型：
    - general: 一般问题
    - specific: 特定问题
    - comparison: 比较问题
    - summary: 总结问题
    """
    try:
        # 验证查询内容
        if not query_request.question.strip():
            raise HTTPException(status_code=400, detail="问题不能为空")
        
        if len(query_request.question) > 1000:
            raise HTTPException(status_code=400, detail="问题长度不能超过1000个字符")
        
        # 获取查询服务
        query_service = QueryService()
        
        # 处理查询
        response = await query_service.process_query(
            db=db,
            request=query_request
        )
        
        logger.info(f"查询处理完成: {query_request.question[:50]}...")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询处理失败: {str(e)}")


@router.get("/history", response_model=List[QueryHistoryResponse], summary="获取查询历史")
async def get_query_history(
    skip: int = 0,
    limit: int = 50,
    query_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    获取查询历史记录
    支持分页、类型过滤和时间范围过滤
    """
    try:
        query_service = QueryService()
        
        history = await query_service.get_query_history(
            db=db,
            skip=skip,
            limit=limit,
            query_type=query_type,
            start_date=start_date,
            end_date=end_date
        )
        
        return [
            QueryHistoryResponse(
                id=record.id,
                question=record.question,
                answer=record.answer,
                query_type=record.query_type,
                response_time=record.response_time,
                chunks_used=record.chunks_used,
                similarity_scores=eval(record.similarity_scores) if record.similarity_scores else [],
                feedback_rating=record.feedback_rating,
                feedback_comment=record.feedback_comment,
                created_at=record.created_at,
                metadata=eval(record.metadata) if record.metadata else {}
            )
            for record in history
        ]
        
    except Exception as e:
        logger.error(f"获取查询历史失败: {e}")
        raise HTTPException(status_code=500, detail="获取查询历史失败")


@router.get("/history/{query_id}", response_model=QueryHistoryResponse, summary="获取查询详情")
async def get_query_detail(query_id: int, db: Session = Depends(get_db)):
    """获取指定查询的详细信息"""
    try:
        query_record = db.query(QueryHistory).filter(QueryHistory.id == query_id).first()
        
        if not query_record:
            raise HTTPException(status_code=404, detail="查询记录不存在")
        
        return QueryHistoryResponse(
            id=query_record.id,
            question=query_record.question,
            answer=query_record.answer,
            query_type=query_record.query_type,
            response_time=query_record.response_time,
            chunks_used=query_record.chunks_used,
            similarity_scores=eval(query_record.similarity_scores) if query_record.similarity_scores else None,
            feedback_rating=query_record.feedback_rating,
            feedback_comment=query_record.feedback_comment,
            created_at=query_record.created_at,
            metadata=eval(query_record.metadata) if query_record.metadata else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取查询详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取查询详情失败")


@router.post("/history/{query_id}/feedback", summary="提交查询反馈")
async def submit_feedback(
    query_id: int,
    feedback: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """为查询结果提交反馈"""
    try:
        query_service = QueryService()
        
        success = query_service.update_query_feedback(
            db=db,
            query_id=query_id,
            rating=feedback.rating,
            comment=feedback.comment
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="查询记录不存在")
        
        logger.info(f"查询反馈提交成功: {query_id}, 评分: {feedback.rating}")
        
        return {"message": "反馈提交成功", "query_id": query_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交查询反馈失败: {e}")
        raise HTTPException(status_code=500, detail="提交查询反馈失败")


@router.get("/statistics", response_model=QueryStatistics, summary="获取查询统计信息")
async def get_query_statistics(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    获取查询统计信息
    包括查询数量、平均响应时间、用户满意度等
    """
    try:
        query_service = QueryService()
        
        stats = await query_service.get_query_statistics(db=db, days=days)
        
        return stats
        
    except Exception as e:
        logger.error(f"获取查询统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取查询统计失败")


@router.post("/batch", response_model=List[QueryResponse], summary="批量查询")
async def batch_query(
    questions: List[str],
    request: Request,
    query_type: str = "general",
    db: Session = Depends(get_db)
):
    """
    批量处理多个查询
    注意：批量查询可能需要较长时间
    """
    try:
        # 验证批量查询限制
        if len(questions) > 10:
            raise HTTPException(status_code=400, detail="批量查询最多支持10个问题")
        
        if not questions:
            raise HTTPException(status_code=400, detail="问题列表不能为空")
        
        # 验证每个问题
        for i, question in enumerate(questions):
            if not question.strip():
                raise HTTPException(status_code=400, detail=f"第{i+1}个问题不能为空")
            if len(question) > 1000:
                raise HTTPException(status_code=400, detail=f"第{i+1}个问题长度不能超过1000个字符")
        
        query_service = QueryService()
        responses = []
        
        # 逐个处理查询
        for question in questions:
            try:
                response = await query_service.process_query(
                    db=db,
                    question=question,
                    query_type=query_type
                )
                responses.append(response)
            except Exception as e:
                # 单个查询失败时，添加错误响应
                error_response = QueryResponse(
                    question=question,
                    answer=f"查询处理失败: {str(e)}",
                    query_type=query_type,
                    response_time=0.0,
                    chunks_used=0,
                    retrieved_chunks=[],
                    confidence_score=0.0,
                    query_id=None
                )
                responses.append(error_response)
                logger.error(f"批量查询中单个问题处理失败: {question[:50]}... - {e}")
        
        logger.info(f"批量查询完成: {len(questions)}个问题")
        
        return responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量查询失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量查询失败: {str(e)}")


@router.post("/suggest", response_model=List[str], summary="获取查询建议")
async def get_query_suggestions(
    partial_query: str,
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """
    基于历史查询获取查询建议
    """
    try:
        if len(partial_query.strip()) < 2:
            return []
        
        # 从历史查询中搜索相似问题
        similar_queries = db.query(QueryHistory.question).filter(
            QueryHistory.question.contains(partial_query.strip())
        ).distinct().limit(limit).all()
        
        suggestions = [query[0] for query in similar_queries]
        
        # 如果历史查询不足，可以添加一些预定义的建议
        if len(suggestions) < limit:
            predefined_suggestions = [
                "这份保险的保障范围是什么？",
                "保险费用如何计算？",
                "理赔流程是怎样的？",
                "保险的免赔额是多少？",
                "保险期限是多长时间？"
            ]
            
            for suggestion in predefined_suggestions:
                if partial_query.lower() in suggestion.lower() and suggestion not in suggestions:
                    suggestions.append(suggestion)
                    if len(suggestions) >= limit:
                        break
        
        return suggestions[:limit]
        
    except Exception as e:
        logger.error(f"获取查询建议失败: {e}")
        return []


@router.delete("/history/{query_id}", summary="删除查询记录")
async def delete_query_history(query_id: int, db: Session = Depends(get_db)):
    """删除指定的查询历史记录"""
    try:
        query_record = db.query(QueryHistory).filter(QueryHistory.id == query_id).first()
        
        if not query_record:
            raise HTTPException(status_code=404, detail="查询记录不存在")
        
        db.delete(query_record)
        db.commit()
        
        logger.info(f"查询记录删除成功: {query_id}")
        
        return {"message": "查询记录删除成功", "query_id": query_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除查询记录失败: {e}")
        raise HTTPException(status_code=500, detail="删除查询记录失败")


@router.post("/clear-history", summary="清空查询历史")
async def clear_query_history(
    confirm: bool = False,
    days: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    清空查询历史记录
    confirm: 确认清空
    days: 清空指定天数前的记录，不指定则清空全部
    """
    try:
        if not confirm:
            raise HTTPException(status_code=400, detail="请确认清空操作")
        
        query = db.query(QueryHistory)
        
        if days:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query = query.filter(QueryHistory.created_at < cutoff_date)
            deleted_count = query.count()
            query.delete()
        else:
            deleted_count = query.count()
            query.delete()
        
        db.commit()
        
        logger.info(f"查询历史清空完成: 删除了{deleted_count}条记录")
        
        return {
            "message": "查询历史清空成功",
            "deleted_count": deleted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清空查询历史失败: {e}")
        raise HTTPException(status_code=500, detail="清空查询历史失败")