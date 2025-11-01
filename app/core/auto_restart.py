"""
自动重启机制模块：提供服务监控和自动重启功能
"""

import os
import sys
import time
import signal
import psutil
import threading
from typing import Optional, Callable, Dict, Any
from datetime import datetime

from app.core.structured_logger import get_structured_logger


class ServiceMonitor:
    """
    服务监控器：负责周期性运行健康检查，并在需要时重启进程
    """

    def __init__(
        self,
        check_interval: int = 30,
        max_restart_attempts: int = 3,
        restart_cooldown: int = 60,
        log_file: Optional[str] = None,
    ) -> None:
        self.check_interval = check_interval
        self.max_restart_attempts = max_restart_attempts
        self.restart_cooldown = restart_cooldown

        self.logger = get_structured_logger("service_monitor", log_file)
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.restart_count = 0
        self.last_restart_time: Optional[datetime] = None

        # 健康检查函数字典
        self.health_checks: Dict[str, Callable[[], bool]] = {}

        # 进程信息
        self.process_pid = os.getpid()
        self.start_time = datetime.now()

        # 注册信号处理
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def add_health_check(self, name: str, check_func: Callable[[], bool]) -> None:
        """
        添加健康检查函数

        - name: 检查名称
        - check_func: 检查函数，返回 True 表示健康
        """
        self.health_checks[name] = check_func
        self.logger.info("health_check_added", check_name=name)

    def _signal_handler(self, signum, frame) -> None:
        """信号处理"""
        self.logger.info("signal_received", signal=signum)
        self.stop_monitoring()

    def _check_process_health(self) -> bool:
        """检查进程健康状态"""
        try:
            process = psutil.Process(self.process_pid)
            if not process.is_running():
                self.logger.error("process_not_running", pid=self.process_pid)
                return False

            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > 1024:
                self.logger.warning("high_memory_usage", memory_mb=memory_mb)

            cpu_percent = process.cpu_percent()
            if cpu_percent > 80:
                self.logger.warning("high_cpu_usage", cpu_percent=cpu_percent)

            return True
        except psutil.NoSuchProcess:
            self.logger.error("process_not_found", pid=self.process_pid)
            return False
        except Exception as e:
            self.logger.log_error(e, {"operation": "process_health_check"})
            return False

    def _run_health_checks(self) -> Dict[str, bool]:
        """运行所有健康检查"""
        results: Dict[str, bool] = {}
        for name, check_func in self.health_checks.items():
            try:
                result = check_func()
                results[name] = result
                if not result:
                    self.logger.warning("health_check_failed", check_name=name)
            except Exception as e:
                results[name] = False
                self.logger.log_error(e, {"operation": "health_check", "check_name": name})
        return results

    def _should_restart(self, health_results: Dict[str, bool]) -> bool:
        """判断是否应该重启服务"""
        if self.last_restart_time:
            time_since_restart = datetime.now() - self.last_restart_time
            if time_since_restart.total_seconds() < self.restart_cooldown:
                return False

        if self.restart_count >= self.max_restart_attempts:
            self.logger.error(
                "max_restart_attempts_reached",
                restart_count=self.restart_count,
                max_attempts=self.max_restart_attempts,
            )
            return False

        if not self._check_process_health():
            return True

        failed_checks = [name for name, ok in health_results.items() if not ok]
        if failed_checks:
            self.logger.warning("health_checks_failed", failed_checks=failed_checks)
            return len(failed_checks) > len(health_results) / 2
        return False

    def _restart_service(self) -> None:
        """重启服务"""
        self.restart_count += 1
        self.last_restart_time = datetime.now()

        self.logger.info(
            "service_restart_initiated",
            restart_count=self.restart_count,
            uptime_seconds=(datetime.now() - self.start_time).total_seconds(),
        )

        try:
            current_process = psutil.Process(self.process_pid)
            cmdline = current_process.cmdline()
            os.execv(sys.executable, [sys.executable] + cmdline[1:])
        except Exception as e:
            self.logger.log_error(e, {"operation": "service_restart"})
            os._exit(1)

    def _monitor_loop(self) -> None:
        """监控循环"""
        self.logger.info(
            "monitoring_started",
            check_interval=self.check_interval,
            max_restart_attempts=self.max_restart_attempts,
        )
        while self.is_monitoring:
            try:
                health_results = self._run_health_checks()
                self.logger.debug("health_check_completed", results=health_results)
                if self._should_restart(health_results):
                    self._restart_service()
                    break
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.log_error(e, {"operation": "monitor_loop"})
                time.sleep(self.check_interval)

    def start_monitoring(self) -> None:
        """开始监控"""
        if self.is_monitoring:
            self.logger.warning("monitoring_already_started")
            return
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("monitoring_thread_started")

    def stop_monitoring(self) -> None:
        """停止监控"""
        if not self.is_monitoring:
            return
        self.is_monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        self.logger.info("monitoring_stopped")

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        uptime = datetime.now() - self.start_time
        return {
            "is_monitoring": self.is_monitoring,
            "restart_count": self.restart_count,
            "last_restart_time": self.last_restart_time.isoformat() if self.last_restart_time else None,
            "uptime_seconds": uptime.total_seconds(),
            "process_pid": self.process_pid,
            "health_checks_count": len(self.health_checks),
        }


class AutoRestartManager:
    """自动重启管理器"""

    _instance: Optional[ServiceMonitor] = None

    @classmethod
    def initialize(cls, **kwargs) -> ServiceMonitor:
        """
        初始化自动重启管理器

        Returns:
            ServiceMonitor: 服务监控器实例
        """
        if cls._instance is None:
            cls._instance = ServiceMonitor(**kwargs)
        return cls._instance

    @classmethod
    def get_instance(cls) -> Optional[ServiceMonitor]:
        """获取管理器实例"""
        return cls._instance

    @classmethod
    def start(cls) -> None:
        """启动监控"""
        if cls._instance:
            cls._instance.start_monitoring()

    @classmethod
    def stop(cls) -> None:
        """停止监控"""
        if cls._instance:
            cls._instance.stop_monitoring()


def setup_auto_restart(
    check_interval: int = 30,
    max_restart_attempts: int = 3,
    restart_cooldown: int = 60,
    log_file: Optional[str] = None,
) -> ServiceMonitor:
    """
    设置自动重启功能

    Returns:
        ServiceMonitor: 服务监控器实例
    """
    return AutoRestartManager.initialize(
        check_interval=check_interval,
        max_restart_attempts=max_restart_attempts,
        restart_cooldown=restart_cooldown,
        log_file=log_file,
    )

