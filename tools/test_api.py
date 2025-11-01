#!/usr/bin/env python3
"""
InsurIntellect Agent API 测试脚本
测试系统的主要 API 端点功能
"""

import requests
import time
from app.core.app_logging import setup_logging, get_logger


BASE_URL = "http://localhost:8001"

# 初始化日志
logger = setup_logging()


def test_health_endpoint() -> bool:
    """测试健康检查端点。"""
    logger.info("🔍 测试健康检查端点...")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/health/", timeout=10)
        logger.info(f"状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            logger.info("✅ 健康检查成功")
            logger.info(f"   状态: {data.get('status', 'unknown')}")
            logger.info(f"   数据库: {data.get('database_status', 'unknown')}")
            logger.info(f"   向量数据库: {data.get('vector_db_status', 'unknown')}")
            logger.info(f"   模型: {data.get('llm_status', 'unknown')}")
            return True
        else:
            logger.error(f"❌ 健康检查失败 HTTP {response.status_code}")
            logger.error(f"   错误响应: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ 健康检查异常: {e}")
        return False


def test_query_endpoint_correct() -> bool:
    """测试查询端点。"""
    logger.info("\n🔍 测试查询端点 (/api/v1/queries/ask)...")
    try:
        data = {
            "question": "什么是车险？",
            "query_type": "general",
            "max_chunks": 3,
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/queries/ask",
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        logger.info(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ 查询成功")
            logger.info(f"   答案长度: {len(result.get('answer', ''))}")
            logger.info(f"   相关文档数: {len(result.get('sources', []))}")
            logger.info(f"   响应时间: {result.get('response_time', 'N/A')}")
            return True
        else:
            logger.error(f"❌ 查询失败: HTTP {response.status_code}")
            logger.error(f"   错误响应: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ 查询异常: {e}")
        return False


def test_alternative_health_endpoints() -> bool:
    """测试其他健康检查端点。"""
    logger.info("\n🔍 测试其他健康检查端点...")

    endpoints = [
        ("存活检查", f"{BASE_URL}/api/v1/health/live"),
        ("就绪检查", f"{BASE_URL}/api/v1/health/ready"),
        ("模型信息", f"{BASE_URL}/api/v1/health/model"),
    ]

    results = []
    for name, url in endpoints:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ {name}: 成功")
                data = response.json()
                if name == "模型信息":
                    logger.info(f"   模型: {data.get('model', 'Unknown')}")
                    logger.info(f"   状态: {data.get('status', 'Unknown')}")
                results.append(True)
            else:
                logger.error(f"❌ {name}: HTTP {response.status_code}")
                results.append(False)
        except Exception as e:
            logger.error(f"❌ {name}: 异常 - {e}")
            results.append(False)

    return all(results)


def test_frontend_and_docs() -> tuple[int, int]:
    """测试前端和文档端点。"""
    logger.info("\n📋 测试基础端点...")
    basic_endpoints = [
        ("根路径", f"{BASE_URL}/"),
        ("API 信息", f"{BASE_URL}/api"),
        ("API 文档", f"{BASE_URL}/docs"),
    ]

    passed = 0
    for name, url in basic_endpoints:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ {name}: 成功")
                passed += 1
            else:
                logger.error(f"❌ {name}: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"❌ {name}: 异常 - {e}")

    return passed, len(basic_endpoints)


def main():
    logger.info("🚀 开始 API 端点测试...")
    logger.info("=" * 50)

    # 1. 基础端点
    basic_passed, basic_total = test_frontend_and_docs()

    # 2. 主健康检查
    health_result = test_health_endpoint()

    # 3. 其他健康检查
    alt_health_result = test_alternative_health_endpoints()

    # 4. 查询端点
    query_result = test_query_endpoint_correct()

    # 总结
    logger.info("\n" + "=" * 50)
    logger.info("📊 测试结果总结:")
    logger.info("=" * 50)

    total_passed = basic_passed + (1 if health_result else 0) + (1 if alt_health_result else 0) + (1 if query_result else 0)
    total_tests = basic_total + 3

    logger.info(f"基础端点: {basic_passed}/{basic_total}")
    logger.info(f"主健康检查: {'1/1' if health_result else '0/1'}")
    logger.info(f"其他健康检查: {'1/1' if alt_health_result else '0/1'}")
    logger.info(f"查询端点: {'1/1' if query_result else '0/1'}")
    logger.info("-" * 50)
    logger.info(f"🎯 总体结果: {total_passed}/{total_tests} 测试通过")

    if total_passed == total_tests:
        logger.info("🎉 所有测试通过! API 服务运行正常。")
    else:
        logger.warning("⚠️  部分测试失败，请检查服务配置。")


if __name__ == "__main__":
    main()
