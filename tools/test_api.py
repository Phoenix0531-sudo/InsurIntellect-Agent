#!/usr/bin/env python3
"""
InsurIntellect Agent API 测试脚本
测试系统的主要 API 端点功能
"""

import os
import requests
import time
from app.core.app_logging import setup_logging, get_logger


# 支持环境变量配置，默认使用本地 8000
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

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
            headers={"Content-Type": "application/json; charset=utf-8"},
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

    # 5. 新增：异常路径也返回 query_id 的自检
    ask_query_id_ok = test_ask_returns_query_id_even_on_error()

    # 6. 新增：历史计数随 ask 增加的自检
    history_increase_ok = test_history_count_increases_after_ask()

    # 7. 新增：session_id 持久化与改写元数据键存在的自检
    session_meta_ok = test_session_id_and_rewriting_metadata_saved()

    # 总结
    logger.info("\n" + "=" * 50)
    logger.info("📊 测试结果总结:")
    logger.info("=" * 50)

    total_passed = (
        basic_passed
        + (1 if health_result else 0)
        + (1 if alt_health_result else 0)
        + (1 if query_result else 0)
        + (1 if ask_query_id_ok else 0)
        + (1 if history_increase_ok else 0)
        + (1 if session_meta_ok else 0)
    )
    total_tests = basic_total + 6

    logger.info(f"基础端点: {basic_passed}/{basic_total}")
    logger.info(f"主健康检查: {'1/1' if health_result else '0/1'}")
    logger.info(f"其他健康检查: {'1/1' if alt_health_result else '0/1'}")
    logger.info(f"查询端点: {'1/1' if query_result else '0/1'}")
    logger.info(f"异常路径 query_id: {'1/1' if ask_query_id_ok else '0/1'}")
    logger.info(f"历史计数递增: {'1/1' if history_increase_ok else '0/1'}")
    logger.info(f"session_id 与改写元数据: {'1/1' if session_meta_ok else '0/1'}")
    logger.info("-" * 50)
    logger.info(f"🎯 总体结果: {total_passed}/{total_tests} 测试通过")

    if total_passed == total_tests:
        logger.info("🎉 所有测试通过! API 服务运行正常。")
    else:
        logger.warning("⚠️  部分测试失败，请检查服务配置。")


 

def test_ask_returns_query_id_even_on_error() -> bool:
    """自检：无模型/密钥时也应返回非空 query_id。"""
    logger.info("\n🔍 自检：异常路径也返回 query_id ...")
    try:
        payload = {"question": "测试：没有API密钥时也应返回 query_id", "query_type": "general"}
        r = requests.post(
            f"{BASE_URL}/api/v1/queries/ask",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30,
        )
        logger.info(f"状态码: {r.status_code}")
        if r.status_code != 200:
            logger.error(f"❌ /queries/ask 返回 {r.status_code}")
            return False
        body = r.json()
        qid = body.get("query_id")
        ok = isinstance(qid, int) and qid > 0
        if ok:
            logger.info(f"✅ query_id 非空: {qid}")
        else:
            logger.error(f"❌ query_id 非法: {qid}")
        return ok
    except Exception as e:
        logger.error(f"❌ 自检异常: {e}")
        return False


def _get_history_count_and_items() -> tuple[int, list]:
    try:
        r = requests.get(f"{BASE_URL}/api/v1/queries/history", timeout=15)
        if r.status_code != 200:
            logger.error(f"❌ /queries/history 返回 {r.status_code}")
            return 0, []
        data = r.json()
        # 兼容不同结构：优先 {items:[...], total_count:n}；兼容旧 {Count:n}；或纯列表
        if isinstance(data, dict):
            items = data.get("items") or data.get("history") or []
            count = data.get("total_count")
            if count is None:
                count = data.get("Count")
            if count is None:
                count = len(items)
            return int(count), items
        elif isinstance(data, list):
            return len(data), data
        else:
            return 0, []
    except Exception as e:
        logger.error(f"❌ 获取历史异常: {e}")
        return 0, []


def test_history_count_increases_after_ask() -> bool:
    """自检：调用 /ask 后，历史计数应增加且 ID 对应。"""
    logger.info("\n🔍 自检：/ask 后历史计数递增 ...")
    before_count, _ = _get_history_count_and_items()
    logger.info(f"调用前历史计数: {before_count}")

    # 触发一次 ask
    payload = {"question": "自检：计数递增校验", "query_type": "general"}
    r = requests.post(
        f"{BASE_URL}/api/v1/queries/ask",
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    if r.status_code != 200:
        logger.error(f"❌ /queries/ask 返回 {r.status_code}")
        return False
    qid = r.json().get("query_id")

    # 再次获取历史
    after_count, items = _get_history_count_and_items()
    logger.info(f"调用后历史计数: {after_count}")

    inc_ok = after_count >= before_count + 1
    id_ok = any((item.get("id") == qid) for item in items) if items and isinstance(qid, int) else True

    if inc_ok:
        logger.info("✅ 历史计数递增")
    else:
        logger.error("❌ 历史计数未递增")
    if isinstance(qid, int):
        if id_ok:
            logger.info(f"✅ 历史中存在对应 ID: {qid}")
        else:
            logger.warning(f"⚠️ 历史未找到对应 ID: {qid}（可能被截断或分页）")

    return inc_ok and (id_ok or not isinstance(qid, int))


def test_session_id_and_rewriting_metadata_saved() -> bool:
    """自检：发送 session_id，验证历史持久化与改写元数据键存在。

    说明：
    - 无需依赖改写开启；仅断言响应详情的 metadata 中存在 'rewriting_metadata' 键，
      该键由数据库列 QueryHistory.rewriting_metadata_json 解析产生；
    - 始终断言 query_id 持久化并可通过详情接口获取。
    """
    logger.info("\n🔍 自检：session_id 持久化与改写元数据键存在 ...")
    try:
        sid = f"test-session-{int(time.time())}"
        payload = {
            "question": "多轮会话测试：校验 session 与改写元数据",
            "query_type": "general",
            "session_id": sid
        }
        r = requests.post(
            f"{BASE_URL}/api/v1/queries/ask",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30,
        )
        if r.status_code != 200:
            logger.error(f"❌ /queries/ask 返回 {r.status_code}")
            return False
        body = r.json()
        qid = body.get("query_id")
        if not isinstance(qid, int) or qid <= 0:
            logger.error(f"❌ 非法 query_id: {qid}")
            return False

        # 查询详情以检查 metadata
        d = requests.get(f"{BASE_URL}/api/v1/queries/history/{qid}", timeout=20)
        if d.status_code != 200:
            logger.error(f"❌ /queries/history/{qid} 返回 {d.status_code}")
            return False
        detail = d.json()
        metadata = detail.get("metadata") or {}
        has_rewriting_key = "rewriting_metadata" in metadata
        has_rewritten_key = "rewritten_query" in metadata

        if has_rewriting_key and has_rewritten_key:
            logger.info("✅ metadata 中包含改写相关键（来源于 rewriting_metadata_json）")
            return True
        else:
            logger.error("❌ metadata 缺少改写相关键")
            return False
    except Exception as e:
        logger.error(f"❌ 自检异常: {e}")
        return False


if __name__ == "__main__":
    main()
