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

    # 服务器配置（作品集演示默认本机 8766，避免 5000/8765/8748）
    HOST: str = Field(default="127.0.0.1", description="服务器主机")
    PORT: int = Field(default=8766, description="服务器端口")
    RELOAD: bool = Field(default=True, description="自动重载")

    # OpenAI-compatible provider（优先 new-api / 任意 OpenAI 兼容网关）
    OPENAI_API_KEY: str = Field(default="", description="OpenAI-compatible API 密钥")
    OPENAI_BASE_URL: str = Field(
        default="http://127.0.0.1:31876/v1",
        description="OpenAI-compatible API 基础 URL",
    )
    OPENAI_MODEL: str = Field(default="gpt-5.4", description="OpenAI模型（兼容旧字段）")
    OPENAI_MODEL_LIGHT: str = Field(default="gpt-5.4", description="轻量任务模型（意图/重写/路由）")
    OPENAI_MODEL_CORE: str = Field(default="gpt-5.4", description="核心生成模型（答案生成/摘要）")
    # Prefer real local HF embedding when available; fall back to local:hash offline.
    # Clash/proxy may be required once to download; thereafter uses HF hub cache.
    OPENAI_EMBEDDING_MODEL: str = Field(
        default="hf:BAAI/bge-small-zh-v1.5",
        description="嵌入模型：hf:<name> 本地 sentence-transformers；local:hash 离线哈希回退",
    )
    OPENAI_MAX_TOKENS: int = Field(default=1000, description="最大令牌数")
    OPENAI_TEMPERATURE: float = Field(default=0.2, description="温度参数")
    OPENAI_TIMEOUT_SECS: int = Field(default=90, description="LLM客户端超时（秒）")

    # 硅基流动配置（兼容回退；演示默认清空以免误走）
    SILICONFLOW_API_KEY: str = Field(default="", description="硅基流动API密钥（可选回退）")
    SILICONFLOW_BASE_URL: str = Field(default="", description="硅基流动API基础URL（可选回退）")
    SILICONFLOW_MODEL: str = Field(default="", description="硅基流动模型（可选回退）")

    # 向量数据库配置
    VECTOR_DB_TYPE: str = Field(default="chroma", description="向量数据库类型")
    CHROMA_PERSIST_DIRECTORY: str = Field(
        default="./data/vector_db/chroma", description="ChromaDB持久化目录"
    )
    PINECONE_API_KEY: Optional[str] = Field(default=None, description="Pinecone API密钥")
    PINECONE_ENVIRONMENT: Optional[str] = Field(default=None, description="Pinecone环境")
    PINECONE_INDEX_NAME: str = Field(default="insurintellect", description="Pinecone索引名称")

    # 兼容性配置
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-m3", description="嵌入模型（兼容性）")

    # 数据库配置
    DATABASE_URL: str = Field(default="sqlite:///./data/database/app.db", description="数据库URL")

    # 文件上传配置（作品集 v1 不提供 UI 上传；预置 samples/ + simple_ingest.py）
    ALLOWED_FILE_TYPES: List[str] = Field(default=["pdf"], description="允许的文件类型")
    PDF_STORAGE_PATH: str = Field(default="./data/documents/pdfs", description="PDF文件存储路径")
    PROCESSED_DATA_PATH: str = Field(default="./data/processed", description="处理后数据存储路径")

    # 文档处理配置
    CHUNK_SIZE: int = Field(default=400, description="文档块大小")
    CHUNK_OVERLAP: int = Field(default=40, description="文档块重叠")

    # 查询配置
    MAX_RETRIEVED_CHUNKS: int = Field(default=8, description="最大检索块数")
    # bge-small-zh cosine typically ~0.45–0.75 on-topic; hash embeds need much lower.
    SIMILARITY_THRESHOLD: float = Field(
        default=0.32,
        description="相似度阈值（bge 真向量建议 0.30–0.40；local:hash 可降到 0.05）",
    )

    # 查询重写与路由配置（主演示默认关闭）
    ENABLE_QUERY_REWRITING: bool = Field(default=False, description="启用口语化查询意图转换引擎")
    ENABLE_QUERY_ROUTING: bool = Field(
        default=False, description="启用基于 LLM 的 RAG/SQL 路由（关闭则默认走 RAG）"
    )
    SIMPLE_RAG_MODE: bool = Field(
        default=True,
        description="主路径：retrieve topk → generate；关闭后才走 SQL/KG 等 advanced 旁路",
    )
    ONTOLOGY_JSON_PATH: str = Field(
        default="tools/insurance_ontology.json", description="保险术语本体库JSON路径"
    )

    # 时序与降级超时（演示需能完成一次真实生成；勿过小误伤）
    CONTEXT_BUILD_TIMEOUT_SECS: int = Field(default=20, description="检索上下文构建最大等待秒数")
    LLM_ANSWER_TIMEOUT_SECS: int = Field(
        default=60, description="非流式回答最大等待秒数，超时将返回降级提示"
    )
    LLM_QUEUE_TIMEOUT_SECS: float = Field(
        default=5.0, description="等待全局并发队列信号量的最大秒数，超时则快速降级"
    )

    # 监控和自动重启设置（默认关闭；演示用 uvicorn 自带重载即可）
    ENABLE_AUTO_RESTART: bool = Field(default=False, description="启用自动重启功能")
    MAX_RESTART_ATTEMPTS: int = Field(default=3, description="最大重启尝试次数")
    RESTART_COOLDOWN: int = Field(default=60, description="重启冷却时间（秒）")

    # 结构化日志设置
    ENABLE_STRUCTURED_LOGGING: bool = Field(default=True, description="启用结构化日志")
    STRUCTURED_LOG_FILE: str = Field(default="logs/structured.log", description="结构化日志文件路径")

    # 后台任务配置
    CELERY_BROKER_URL: Optional[str] = Field(default=None, description="Celery代理URL（仅配置占位，当前主路径不依赖 Celery）")
    CELERY_RESULT_BACKEND: Optional[str] = Field(default=None, description="Celery结果后端")

    # LLM 并发与可靠性控制
    LLM_MAX_CONCURRENCY: int = Field(default=20, description="LLM 并发限制（全局Semaphore）")
    LLM_MAX_RETRIES: int = Field(default=3, description="LLM 最大重试次数（含初次调用）")
    LLM_BACKOFF_BASE: float = Field(default=0.25, description="LLM 退避基准秒")
    LLM_BACKOFF_FACTOR: float = Field(default=2.0, description="LLM 退避增长因子")
    LLM_BACKOFF_MAX: float = Field(default=2.5, description="LLM 最大退避秒")
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = Field(default=10, description="LLM 熔断失败阈值")
    LLM_CIRCUIT_RESET_TIMEOUT: int = Field(default=30, description="LLM 熔断冷却秒")
    LLM_DAILY_TOKENS_LIMIT: int = Field(
        default=0, description="每日令牌上限（0表示不限制，需结合外部监控）"
    )
    CHROMA_THREAD_MAX_WORKERS: int = Field(default=32, description="ChromaDB 同步调用线程池大小")
    DATABASE_URL_ASYNC: str = Field(default="", description="异步数据库URL（postgresql+asyncpg...）")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Windows .env often uses CRLF; strip CR so empty/async URLs stay valid.
        self._sanitize_string_fields()
        self._create_directories()
        try:
            if (self.OPENAI_MODEL_CORE or "").strip() == "":
                self.OPENAI_MODEL_CORE = self.OPENAI_MODEL
            if (self.OPENAI_MODEL_LIGHT or "").strip() == "":
                self.OPENAI_MODEL_LIGHT = self.OPENAI_MODEL
        except Exception:
            pass

    def _sanitize_string_fields(self) -> None:
        for name, value in list(self.__dict__.items()):
            if isinstance(value, str):
                cleaned = value.replace(chr(13), "").strip()
                if cleaned != value:
                    object.__setattr__(self, name, cleaned)

    def _create_directories(self):
        """创建必要的目录"""
        directories = [
            Path("./data/documents/pdfs"),
            Path("./data/vector_db/chroma"),
            Path("./data/processed"),
            Path("./data/database"),
            Path("./logs"),
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


# 全局配置实例
settings = Settings()
