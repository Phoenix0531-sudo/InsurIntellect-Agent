"""
主API路由
整合所有子路由
"""

from fastapi import APIRouter
from app.api.endpoints import documents, queries, admin, health

api_router = APIRouter()

# 包含各个子路由
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(queries.router, prefix="/queries", tags=["queries"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])