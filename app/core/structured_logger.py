# -*- coding: utf-8 -*-
"""
结构化日志模块
提供JSON格式的结构化日志记录功能
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class StructuredLogger:
    """结构化日志记录器"""
    
    def __init__(self, name: str, log_file: Optional[str] = None):
        """
        初始化结构化日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径（可选）
        """
        self.name = name
        self.logger = logging.getLogger(name)
        
        if not self.logger.handlers:
            # 设置日志级别
            self.logger.setLevel(logging.INFO)
            
            # 创建格式化器
            formatter = logging.Formatter('%(message)s')
            
            # 添加控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            # 如果指定了日志文件,添加文件处理器
            if log_file:
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
    
    def _create_log_entry(self, level: str, event: str, **kwargs) -> Dict[str, Any]:
        """
        创建日志条目
        
        Args:
            level: 日志级别
            event: 事件名称
            **kwargs: 额外数据
            
        Returns:
            Dict[str, Any]: 结构化日志条目
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "logger": self.name,
            "event": event,
            "data": kwargs
        }
    
    def _log(self, level: str, event: str, **kwargs):
        """
        记录日志
        
        Args:
            level: 日志级别
            event: 事件名称
            **kwargs: 额外数据
        """
        log_entry = self._create_log_entry(level, event, **kwargs)
        log_message = json.dumps(log_entry, ensure_ascii=False, indent=2)
        
        # 根据级别选择合适的日志方法
        if level == "DEBUG":
            self.logger.debug(log_message)
        elif level == "INFO":
            self.logger.info(log_message)
        elif level == "WARNING":
            self.logger.warning(log_message)
        elif level == "ERROR":
            self.logger.error(log_message)
        else:
            self.logger.info(log_message)
    
    def info(self, event: str, **kwargs):
        """记录信息级别日志"""
        self._log("INFO", event, **kwargs)
    
    def warning(self, event: str, **kwargs):
        """记录警告级别日志"""
        self._log("WARNING", event, **kwargs)
    
    def error(self, event: str, **kwargs):
        """记录错误级别日志"""
        self._log("ERROR", event, **kwargs)
    
    def debug(self, event: str, **kwargs):
        """记录调试级别日志"""
        self._log("DEBUG", event, **kwargs)
    
    def log_request(self, method: str, path: str, status_code: int, response_time: float, **kwargs):
        """
        记录HTTP请求日志
        
        Args:
            method: HTTP方法
            path: 请求路径
            status_code: 状态码
            response_time: 响应时间
            **kwargs: 额外信息
        """
        self.info(
            "http_request",
            method=method,
            path=path,
            status_code=status_code,
            response_time=response_time,
            **kwargs
        )
    
    def log_query(self, query: str, response_time: float, status: str, **kwargs):
        """
        记录查询处理日志
        
        Args:
            query: 查询内容
            response_time: 响应时间
            status: 处理状态
            **kwargs: 额外信息
        """
        self.info(
            "query_processed",
            query=query,
            response_time=response_time,
            status=status,
            **kwargs
        )
    
    def log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None, **kwargs):
        """
        记录错误日志
        
        Args:
            error: 异常对象
            context: 错误上下文
            **kwargs: 额外信息
        """
        self.error(
            "error_occurred",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            context=context or {},
            **kwargs
        )
    
    def log_performance(self, operation: str, duration: float, **kwargs):
        """
        记录性能日志
        
        Args:
            operation: 操作名称
            duration: 持续时间（秒）
            **kwargs: 额外信息
        """
        level = "WARNING" if duration > 5.0 else "INFO"  # 超过5秒的操作记录为警告
        self._log(
            level,
            "performance_metric",
            operation=operation,
            duration=duration,
            **kwargs
        )
    
    def log_system_event(self, event_type: str, **kwargs):
        """
        记录系统事件日志
        
        Args:
            event_type: 事件类型
            **kwargs: 事件数据
        """
        self.info(
            "system_event",
            event_type=event_type,
            **kwargs
        )


class LoggerManager:
    """日志管理器"""
    
    _loggers: Dict[str, StructuredLogger] = {}
    
    @classmethod
    def get_logger(cls, name: str, log_file: Optional[str] = None) -> StructuredLogger:
        """
        获取或创建日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径（可选）
            
        Returns:
            StructuredLogger: 结构化日志记录器实例
        """
        if name not in cls._loggers:
            cls._loggers[name] = StructuredLogger(name, log_file)
        return cls._loggers[name]
    
    @classmethod
    def clear_loggers(cls):
        """清除所有日志记录器"""
        cls._loggers.clear()


def get_structured_logger(name: str, log_file: Optional[str] = None) -> StructuredLogger:
    """
    便捷函数:获取结构化日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件路径（可选）
        
    Returns:
        StructuredLogger: 结构化日志记录器实例
    """
    return LoggerManager.get_logger(name, log_file)


# 默认的应用日志记录器
app_logger = get_structured_logger("app")


if __name__ == "__main__":
    # 测试代码
    from app.core.app_logging import setup_logging, get_logger
    setup_logging(level="INFO")
    _logger = get_logger(__name__)
    _logger.info("=== 结构化日志测试 ===")

    # 创建测试日志记录器
    test_logger = get_structured_logger("test")

    # 测试各种日志类型
    test_logger.info("应用启动", version="1.0.0", port=8000)
    test_logger.warning("配置警告", message="使用默认配置")
    test_logger.error("测试错误", error_code=500)

    # 测试HTTP请求日志
    test_logger.log_request("GET", "/api/health", 200, 0.05, client_ip="127.0.0.1")

    # 测试查询日志
    test_logger.log_query("什么是保险？", 1.2, "success", results_count=5)

    # 测试性能日志
    test_logger.log_performance("database_query", 0.8)
    test_logger.log_performance("slow_operation", 6.5)  # 这会记录为WARNING

    # 测试系统事件日志
    test_logger.log_system_event("startup", component="main_app")

    _logger.info("结构化日志测试完成")


