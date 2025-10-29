#!/usr/bin/env python3
"""
InsurIntellect Agent API测试脚本
测试系统的主要API端点功能
"""

import requests
import json
import time

def test_health_endpoint():
    """测试健康检查端点"""
    print("🔍 测试健康检查端点...")
    try:
        response = requests.get("http://localhost:8000/api/v1/health/", timeout=10)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康检查成功!")
            print(f"   状态: {data.get('status', 'unknown')}")
            print(f"   数据库: {data.get('database_status', 'unknown')}")
            print(f"   向量数据库: {data.get('vector_db_status', 'unknown')}")
            print(f"   模型状态: {data.get('model_status', 'unknown')}")
            return True
        else:
            print(f"❌ 健康检查失败: HTTP {response.status_code}")
            print(f"   错误响应: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False

def test_query_endpoint_correct():
    """测试正确的查询端点"""
    print("\n🔍 测试查询端点 (/api/v1/queries/ask)...")
    try:
        data = {
            "question": "什么是车险？",
            "query_type": "general",
            "max_chunks": 3
        }
        response = requests.post(
            "http://localhost:8000/api/v1/queries/ask",
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 查询成功!")
            print(f"   答案长度: {len(result.get('answer', ''))}")
            print(f"   相关文档数: {len(result.get('sources', []))}")
            print(f"   响应时间: {result.get('response_time', 'N/A')}秒")
            return True
        else:
            print(f"❌ 查询失败: HTTP {response.status_code}")
            print(f"   错误响应: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 查询异常: {e}")
        return False

def test_alternative_health_endpoints():
    """测试其他健康检查端点"""
    print("\n🔍 测试其他健康检查端点...")
    
    endpoints = [
        ("存活检查", "http://localhost:8000/api/v1/health/live"),
        ("就绪检查", "http://localhost:8000/api/v1/health/ready"),
        ("模型信息", "http://localhost:8000/api/v1/health/model")
    ]
    
    results = []
    for name, url in endpoints:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"✅ {name}: 成功")
                data = response.json()
                if name == "模型信息":
                    print(f"   模型: {data.get('model', 'Unknown')}")
                    print(f"   状态: {data.get('status', 'Unknown')}")
                results.append(True)
            else:
                print(f"❌ {name}: HTTP {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ {name}: 异常 - {e}")
            results.append(False)
    
    return all(results)

def test_document_endpoints():
    """测试文档管理端点（已移除功能）"""
    print("\n🔍 文档管理端点已移除，跳过测试...")
    print("ℹ️  文档管理功能已从系统中移除，专注于问答功能")
    return True

def main():
    """主测试函数"""
    print("🚀 开始API端点测试...")
    print("=" * 50)
    
    # 测试结果统计
    test_results = []
    
    # 1. 测试基础端点
    print("📋 测试基础端点...")
    basic_endpoints = [
        ("根路径", "http://localhost:8000/"),
        ("API信息", "http://localhost:8000/api"),
        ("API文档", "http://localhost:8000/docs")
    ]
    
    basic_passed = 0
    for name, url in basic_endpoints:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"✅ {name}: 成功")
                basic_passed += 1
            else:
                print(f"❌ {name}: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ {name}: 异常 - {e}")
    
    test_results.append(("基础端点", basic_passed, len(basic_endpoints)))
    
    # 2. 测试健康检查端点
    health_result = test_health_endpoint()
    test_results.append(("主健康检查", 1 if health_result else 0, 1))
    
    # 3. 测试其他健康检查端点
    alt_health_result = test_alternative_health_endpoints()
    test_results.append(("其他健康检查", 1 if alt_health_result else 0, 1))
    
    # 4. 测试查询端点
    query_result = test_query_endpoint_correct()
    test_results.append(("查询端点", 1 if query_result else 0, 1))
    
    # 5. 测试文档端点
    doc_result = test_document_endpoints()
    test_results.append(("文档端点", 1 if doc_result else 0, 1))
    
    # 输出测试总结
    print("\n" + "=" * 50)
    print("📊 测试结果总结:")
    print("=" * 50)
    
    total_passed = 0
    total_tests = 0
    
    for test_name, passed, total in test_results:
        total_passed += passed
        total_tests += total
        status = "✅" if passed == total else "❌"
        print(f"{status} {test_name}: {passed}/{total}")
    
    print("-" * 50)
    print(f"🎯 总体结果: {total_passed}/{total_tests} 测试通过")
    
    if total_passed == total_tests:
        print("🎉 所有测试通过! API服务运行正常。")
    else:
        print("⚠️  部分测试失败，请检查服务配置。")

if __name__ == "__main__":
    main()