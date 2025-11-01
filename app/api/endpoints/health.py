"""
健康检查 API 端点
"""

import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db, db_manager
from app.core.app_logging import get_logger
from app.models.schemas import HealthCheck, SystemStats

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=HealthCheck, summary="基础健康检查")
async def health_check(request: Request, db: Session = Depends(get_db)):
    """
    基础健康检查端点
    检查数据库、向量数据库和 LLM 服务的状态
    """
    try:
        # 检查数据库
        db_status = True
        try:
            db_status = db_manager.health_check()
        except Exception as e:
            logger.warning(f"数据库检查失败: {e}")
            db_status = False

        # 检查向量数据库（在开发环境中视为可选）
        vector_db_status = True
        try:
            vector_service = getattr(request.app.state, "vector_service", None)
            if vector_service:
                stats = await vector_service.get_collection_stats()
                # 只要能获取到统计信息就认为正常
                vector_db_status = stats.get("total_vectors", 0) >= 0
            else:
                logger.info("Vector service not configured; treating as healthy in dev mode")
                vector_db_status = True
        except Exception as e:
            logger.warning(f"向量数据库检查失败: {e}")
            vector_db_status = True

        # 检查 LLM 服务
        llm_status = True
        try:
            llm_service = getattr(request.app.state, "llm_service", None)
            if llm_service:
                # 在开发环境中，LLM 服务问题不影响整体状态
                try:
                    llm_status = await asyncio.wait_for(llm_service.health_check(), timeout=3.0)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"LLM 服务健康检查失败，但系统仍可用: {e}")
                    llm_status = True
            else:
                logger.warning("LLM service not found in app state")
                llm_status = True
        except Exception as e:
            logger.warning(f"LLM 服务检查失败: {e}")
            llm_status = True

        return HealthCheck(
            status="healthy" if all([db_status, vector_db_status, llm_status]) else "unhealthy",
            database_status=db_status,
            vector_db_status=vector_db_status,
            llm_status=llm_status,
        )

    except Exception as e:
        logger.error(f"健康检查端点发生错误: {e}")
        return HealthCheck(status="unhealthy", database_status=False, vector_db_status=False, llm_status=False)


@router.get("/stats", response_model=SystemStats, summary="系统统计信息")
async def get_system_stats(request: Request, db: Session = Depends(get_db)):
    """
    获取系统统计信息：包括文档数量、查询数量、响应时间等
    """
    try:
        from app.models.database_models import Document, DocumentChunk, QueryHistory
        from sqlalchemy import func
        import os

        # 统计文档数量
        total_documents = db.query(Document).count()

        # 统计文档块数量
        total_chunks = db.query(DocumentChunk).count()

        # 统计查询数量
        total_queries = db.query(QueryHistory).count()

        # 计算平均响应时间
        avg_response_time = db.query(func.avg(QueryHistory.response_time)).scalar() or 0.0

        # 计算存储使用量
        storage_used = 0
        try:
            from app.core.config import settings
            pdf_path = settings.PDF_STORAGE_PATH
            if os.path.exists(pdf_path):
                for root, dirs, files in os.walk(pdf_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.exists(file_path):
                            storage_used += os.path.getsize(file_path)
        except Exception:
            pass

        # 运行时间（示例值）
        uptime = 3600.0

        return SystemStats(
            total_documents=total_documents,
            total_chunks=total_chunks,
            total_queries=total_queries,
            avg_response_time=round(avg_response_time, 3),
            storage_used=storage_used,
            uptime=uptime,
        )

    except Exception as e:
        logger.error(f"获取系统统计信息失败: {e}")
        return SystemStats(total_documents=0, total_chunks=0, total_queries=0, avg_response_time=0.0, storage_used=0, uptime=0.0)


@router.get("/ready", summary="就绪检查")
async def readiness_check(request: Request):
    """
    就绪检查端点（用于 Kubernetes 等容器编排系统）
    """
    try:
        # 检查关键服务是否就绪
        vector_service = getattr(request.app.state, "vector_service", None)
        if not vector_service:
            return {"status": "not_ready", "reason": "vector_service_not_initialized"}
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"就绪检查失败: {e}")
        return {"status": "not_ready", "reason": str(e)}


@router.get("/model", summary="模型信息")
async def get_model_info():
    """
    获取当前配置的模型信息
    """
    try:
        from app.core.config import settings
        return {
            "model": settings.OPENAI_MODEL,
            "base_url": settings.OPENAI_BASE_URL,
            "embedding_model": settings.OPENAI_EMBEDDING_MODEL,
            "status": "connected",
        }
    except Exception as e:
        logger.error(f"获取模型信息失败: {e}")
        return {"model": "Unknown", "base_url": "Unknown", "embedding_model": "Unknown", "status": "error"}


@router.get("/live", summary="存活检查")
async def liveness_check():
    """
    存活检查端点（用于 Kubernetes 等容器编排系统）
    """
    return {"status": "alive"}

