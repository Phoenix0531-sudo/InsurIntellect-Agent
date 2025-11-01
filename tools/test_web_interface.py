#!/usr/bin/env python3
"""
Web 与 API 端到端冒烟测试
验证前端页面与主要 API 端点可用性
"""

import requests
from app.core.app_logging import setup_logging, get_logger


BASE_URL = "http://localhost:8001"

# 初始化日志
logger = setup_logging()


def check(url: str, name: str, timeout: int = 10) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            logger.info(f"✅ {name} 可访问: {url}")
            return True
        logger.error(f"❌ {name} 访问失败 HTTP {r.status_code}: {url}")
        return False
    except Exception as e:
        logger.error(f"❌ {name} 异常: {e}")
        return False


def test_suite() -> None:
    logger.info("🚀 Web 与 API 冒烟测试开始")
    logger.info("=" * 50)

    tests = [
        ("根页面", f"{BASE_URL}/"),
        ("API 信息", f"{BASE_URL}/api"),
        ("API 文档", f"{BASE_URL}/docs"),
        ("健康检查", f"{BASE_URL}/api/v1/health/"),
        ("就绪检查", f"{BASE_URL}/api/v1/health/ready"),
        ("存活检查", f"{BASE_URL}/api/v1/health/live"),
        ("模型信息", f"{BASE_URL}/api/v1/health/model"),
    ]

    passed = 0
    for name, url in tests:
        if check(url, name):
            passed += 1

    logger.info("-" * 50)
    logger.info(f"🎯 通过 {passed}/{len(tests)} 项")
    if passed == len(tests):
        logger.info("🎉 冒烟测试全部通过")
    else:
        logger.warning("⚠️  冒烟测试存在失败项，请检查服务状态")


if __name__ == "__main__":
    test_suite()
