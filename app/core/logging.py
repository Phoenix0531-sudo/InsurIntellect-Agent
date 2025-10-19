"""日志配置模块
使用标准库logging而不是loguru
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from app.core.config import settings


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    设置日志配置
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        
    Returns:
        配置好的logger实例
    """
    # 创建logger
    logger = logging.getLogger("insurintellect")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除现有的handlers
    logger.handlers.clear()
    
    # 创建formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件handler（如果指定了文件路径）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "insurintellect") -> logging.Logger:
    """
    获取logger实例
    
    Args:
        name: logger名称
        
    Returns:
        logger实例
    """
    return logging.getLogger(name)


# 初始化默认logger
default_logger = setup_logging(
    log_level=settings.LOG_LEVEL,
    log_file="logs/app.log" if Path("logs").exists() else None
)