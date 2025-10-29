"""
数据库配置和管理模块
"""

from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 数据库引擎配置
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.DEBUG
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG
    )

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基础模型类
Base = declarative_base()

# 元数据
metadata = MetaData()


async def init_db():
    """初始化数据库"""
    try:
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
    
    def create_session(self):
        """创建数据库会话"""
        return self.SessionLocal()
    
    def close_session(self, session):
        """关闭数据库会话"""
        session.close()
    
    def health_check(self) -> bool:
        """数据库健康检查"""
        try:
            session = self.create_session()
            try:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))
                return True
            finally:
                session.close()
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False


# 全局数据库管理器实例
db_manager = DatabaseManager()