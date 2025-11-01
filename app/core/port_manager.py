# -*- coding: utf-8 -*-
"""
端口管理器模块
提供端口可用性检查和自动端口查找功能
"""

import socket
import logging
from contextlib import closing
from typing import Optional

logger = logging.getLogger(__name__)


class PortManager:
    """端口管理器类,提供端口相关的实用功能"""
    
    @staticmethod
    def is_port_available(port: int, host: str = "localhost") -> bool:
        """
        检查指定端口是否可用
        
        Args:
            port: 要检查的端口号
            host: 主机地址,默认为localhost
            
        Returns:
            bool: 端口是否可用
        """
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result != 0
        except Exception as e:
            logger.error(f"检查端口 {port} 时发生错误: {e}")
            return False
    
    @staticmethod
    def find_available_port(start_port: int = 8000, max_attempts: int = 10, host: str = "localhost") -> Optional[int]:
        """
        从指定端口开始查找可用端口
        
        Args:
            start_port: 起始端口号
            max_attempts: 最大尝试次数
            host: 主机地址
            
        Returns:
            Optional[int]: 找到的可用端口号,如果没找到则返回None
        """
        for i in range(max_attempts):
            port = start_port + i
            if PortManager.is_port_available(port, host):
                logger.info(f"找到可用端口: {port}")
                return port
        
        logger.warning(f"在 {start_port}-{start_port + max_attempts - 1} 范围内未找到可用端口")
        return None
    
    @staticmethod
    def get_port_with_fallback(preferred_port: int, fallback_start: int = 8000, max_attempts: int = 10) -> int:
        """
        获取端口,优先使用首选端口,如果不可用则自动查找
        
        Args:
            preferred_port: 首选端口
            fallback_start: 备用端口起始值
            max_attempts: 最大尝试次数
            
        Returns:
            int: 可用的端口号
            
        Raises:
            RuntimeError: 如果找不到可用端口
        """
        # 首先尝试首选端口
        if PortManager.is_port_available(preferred_port):
            logger.info(f"使用首选端口: {preferred_port}")
            return preferred_port
        
        logger.warning(f"首选端口 {preferred_port} 不可用,正在查找备用端口...")
        
        # 查找备用端口
        available_port = PortManager.find_available_port(fallback_start, max_attempts)
        if available_port is not None:
            logger.info(f"使用备用端口: {available_port}")
            return available_port
        
        raise RuntimeError(f"无法找到可用端口,已尝试 {preferred_port} 和 {fallback_start}-{fallback_start + max_attempts - 1}")
    
    @staticmethod
    def check_port_conflict(port: int, service_name: str = "Unknown") -> bool:
        """
        检查端口冲突并记录详细信息
        
        Args:
            port: 要检查的端口
            service_name: 服务名称
            
        Returns:
            bool: 是否存在冲突（True表示有冲突）
        """
        if not PortManager.is_port_available(port):
            logger.error(f"端口冲突检测: 端口 {port} 已被占用 (服务: {service_name})")
            return True
        else:
            logger.info(f"端口检查通过: 端口 {port} 可用 (服务: {service_name})")
            return False


def get_available_port(preferred_port: int = 8000) -> int:
    """
    便捷函数:获取可用端口
    
    Args:
        preferred_port: 首选端口号
        
    Returns:
        int: 可用的端口号
    """
    return PortManager.get_port_with_fallback(preferred_port)


if __name__ == "__main__":
    from app.core.app_logging import setup_logging, get_logger
    setup_logging(level="INFO")
    _logger = get_logger(__name__)
    # 测试代码
    _logger.info("=== 端口管理器测试 ===")

    # 测试端口可用性检查
    test_port = 8000
    is_available = PortManager.is_port_available(test_port)
    _logger.info(f"端口 {test_port} 是否可用: {is_available}")

    # 测试查找可用端口
    available_port = PortManager.find_available_port(8000, 5)
    _logger.info(f"找到的可用端口: {available_port}")

    # 测试带回退的端口获取
    try:
        port = PortManager.get_port_with_fallback(8000)
        _logger.info(f"获取到的端口: {port}")
    except RuntimeError as e:
        _logger.error(f"错误: {e}")


