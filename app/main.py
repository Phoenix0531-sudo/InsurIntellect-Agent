"""
InsurIntellect Agent - 主应用入口
智能保险文档问答系统
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.api.routes import api_router


# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log") if Path("logs").exists() else logging.NullHandler()
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("Starting InsurIntellect Agent...")
    
    # 创建必要的目录
    directories = [
        "data/documents/pdfs",
        "data/vector_db/chroma", 
        "data/processed",
        "data/database",
        "logs"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    # 初始化数据库
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # 初始化应用状态
    from app.core.database import db_manager
    from app.services.vector_store import VectorStoreService
    from app.services.llm_service import LLMService
    
    # 设置数据库管理器
    app.state.db_manager = db_manager
    logger.info("Database manager initialized in app state")
    
    # 初始化向量服务
    try:
        vector_service = VectorStoreService()
        await vector_service.initialize()
        app.state.vector_service = vector_service
        logger.info("Vector service initialized in app state")
    except Exception as e:
        logger.error(f"Failed to initialize vector service: {e}")
        # 设置一个空的向量服务以避免属性错误
        app.state.vector_service = None
    
    # 初始化LLM服务
    try:
        llm_service = LLMService()
        app.state.llm_service = llm_service
        logger.info("LLM service initialized in app state")
    except Exception as e:
        logger.error(f"Failed to initialize LLM service: {e}")
        # 设置一个空的LLM服务以避免属性错误
        app.state.llm_service = None
    
    logger.info("InsurIntellect Agent started successfully")
    
    yield
    
    # 关闭时清理
    logger.info("Shutting down InsurIntellect Agent...")


# 创建FastAPI应用实例
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="智能保险文档问答系统 - 基于大语言模型的文档检索与问答服务",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP异常处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """通用异常处理"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "status_code": 500
        }
    )


# 根路径 - 重定向到前端界面
@app.get("/")
async def root():
    """根路径 - 重定向到前端界面"""
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")

# API信息路径
@app.get("/api")
async def api_info():
    """API信息"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "智能保险文档问答系统",
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None
    }


# 包含API路由
app.include_router(api_router, prefix="/api/v1")


# 静态文件服务（如果需要）
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD and settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )