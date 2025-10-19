"""
配置管理模块
使用Pydantic Settings进行环境变量管理
"""

from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """应用配置设置"""
    
    # 应用基本信息
    APP_NAME: str = Field(default="InsurIntellect Agent", description="应用名称")
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    DEBUG: bool = Field(default=True, description="调试模式")
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    
    # 服务器配置
    HOST: str = Field(default="0.0.0.0", description="服务器主机")
    PORT: int = Field(default=8000, description="服务器端口")
    RELOAD: bool = Field(default=True, description="自动重载")
    
    # OpenAI配置 (现在使用硅基流动)
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API密钥")
    OPENAI_BASE_URL: str = Field(default="https://api.siliconflow.cn/v1", description="OpenAI API基础URL")
    OPENAI_MODEL: str = Field(default="Qwen/Qwen2.5-7B-Instruct", description="OpenAI模型")
    OPENAI_EMBEDDING_MODEL: str = Field(default="BAAI/bge-large-zh-v1.5", description="嵌入模型")
    OPENAI_MAX_TOKENS: int = Field(default=1000, description="最大令牌数")
    OPENAI_TEMPERATURE: float = Field(default=0.7, description="温度参数")
    
    # 硅基流动配置
    SILICONFLOW_API_KEY: str = Field(default="", description="硅基流动API密钥")
    SILICONFLOW_BASE_URL: str = Field(default="https://api.siliconflow.cn/v1", description="硅基流动API基础URL")
    SILICONFLOW_MODEL: str = Field(default="Qwen/Qwen2.5-7B-Instruct", description="硅基流动模型")
    
    # 向量数据库配置
    VECTOR_DB_TYPE: str = Field(default="chroma", description="向量数据库类型")
    CHROMA_PERSIST_DIRECTORY: str = Field(default="./data/vector_db/chroma", description="ChromaDB持久化目录")
    PINECONE_API_KEY: Optional[str] = Field(default=None, description="Pinecone API密钥")
    PINECONE_ENVIRONMENT: Optional[str] = Field(default=None, description="Pinecone环境")
    PINECONE_INDEX_NAME: str = Field(default="insurintellect", description="Pinecone索引名称")
    
    # 兼容性配置
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-large-zh-v1.5", description="嵌入模型（兼容性）")
    
    # 数据库配置
    DATABASE_URL: str = Field(default="sqlite:///./data/database/app.db", description="数据库URL")
    DATABASE_ECHO: bool = Field(default=False, description="数据库回显")
    
    # 文件上传配置
    MAX_UPLOAD_SIZE: int = Field(default=10485760, description="最大上传文件大小")  # 10MB
    ALLOWED_FILE_TYPES: List[str] = Field(default=["pdf"], description="允许的文件类型")
    PDF_STORAGE_PATH: str = Field(default="./data/documents/pdfs", description="PDF文件存储路径")
    PROCESSED_DATA_PATH: str = Field(default="./data/processed", description="处理后数据存储路径")
    
    # 文档处理配置
    CHUNK_SIZE: int = Field(default=200, description="文档块大小")  # 进一步减小到200字符以符合512 token限制
    CHUNK_OVERLAP: int = Field(default=20, description="文档块重叠")  # 相应减小重叠
    MAX_CHUNKS_PER_DOCUMENT: int = Field(default=1000, description="每个文档最大块数")
    
    # 查询配置
    MAX_RETRIEVED_CHUNKS: int = Field(default=5, description="最大检索块数")
    SIMILARITY_THRESHOLD: float = Field(default=0.7, description="相似度阈值")
    
    # 安全配置
    SECRET_KEY: str = Field(default="your-secret-key-here", description="密钥")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="访问令牌过期时间")
    
    # 监控配置
    ENABLE_METRICS: bool = Field(default=True, description="启用指标")
    METRICS_PORT: int = Field(default=9090, description="指标端口")
    
    # 后台任务配置
    CELERY_BROKER_URL: Optional[str] = Field(default=None, description="Celery代理URL")
    CELERY_RESULT_BACKEND: Optional[str] = Field(default=None, description="Celery结果后端")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"  # 忽略额外字段
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保必要的目录存在
        self._create_directories()
    
    def _create_directories(self):
        """创建必要的目录"""
        directories = [
            Path("./data/documents/pdfs"),
            Path("./data/vector_db/chroma"),
            Path("./data/processed"),
            Path("./data/database"),
            Path("./logs")
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


# 全局配置实例
settings = Settings()