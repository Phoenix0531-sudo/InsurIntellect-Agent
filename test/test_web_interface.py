#!/usr/bin/env python3
"""
Web界面测试脚本
测试InsurIntellect Agent的Web界面和API功能
"""

import requests
import json
import time
from typing import Dict, Any, List

class WebInterfaceTest:
    """Web界面测试类"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, message: str = "", response_time: float = 0):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "response_time": response_time,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message} ({response_time:.3f}s)")
    
    def test_server_health(self):
        """测试服务器健康状态"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/api")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "服务器健康检查", 
                    True, 
                    f"服务器运行正常 - {data.get('name', 'Unknown')}", 
                    response_time
                )
                return True
            else:
                self.log_test(
                    "服务器健康检查", 
                    False, 
                    f"HTTP {response.status_code}", 
                    response_time
                )
                return False
        except Exception as e:
            self.log_test("服务器健康检查", False, f"连接失败: {str(e)}")
            return False
    
    def test_frontend_access(self):
        """测试前端页面访问"""
        try:
            start_time = time.time()
            response = self.session.get(self.base_url)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                # 检查是否包含HTML内容
                if "InsurIntellect" in response.text and "html" in response.text.lower():
                    self.log_test(
                        "前端页面访问", 
                        True, 
                        "前端页面加载成功", 
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "前端页面访问", 
                        False, 
                        "页面内容异常", 
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "前端页面访问", 
                    False, 
                    f"HTTP {response.status_code}", 
                    response_time
                )
                return False
        except Exception as e:
            self.log_test("前端页面访问", False, f"访问失败: {str(e)}")
            return False
    
    def test_health_endpoint(self):
        """测试健康检查端点"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/api/v1/health/")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "健康检查端点", 
                    True, 
                    f"状态: {data.get('status', 'unknown')}", 
                    response_time
                )
                return True
            else:
                self.log_test(
                    "健康检查端点", 
                    False, 
                    f"HTTP {response.status_code}", 
                    response_time
                )
                return False
        except Exception as e:
            self.log_test("健康检查端点", False, f"请求失败: {str(e)}")
            return False
    
    def test_query_endpoint(self):
        """测试查询端点"""
        test_query = {
            "question": "什么是车险？",
            "query_type": "general",
            "max_chunks": 5
        }
        
        try:
            start_time = time.time()
            response = self.session.post(
                f"{self.base_url}/api/v1/queries/ask",  # 修正端点路径
                json=test_query,
                headers={"Content-Type": "application/json"}
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if "answer" in data:
                    self.log_test(
                        "查询端点测试", 
                        True, 
                        f"查询成功，答案长度: {len(data['answer'])}", 
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "查询端点测试", 
                        False, 
                        "响应格式异常", 
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "查询端点测试", 
                    False, 
                    f"HTTP {response.status_code}", 
                    response_time
                )
                return False
        except Exception as e:
            self.log_test("查询端点测试", False, f"请求失败: {str(e)}")
            return False
    
    def test_documents_endpoint(self):
        """测试文档管理端点 - 已禁用"""
        # 文档管理功能已移除，跳过测试
        print("⚠️  文档管理功能已移除，跳过相关测试")
        return True
        """测试文档管理端点"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/api/v1/documents/")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log_test(
                        "文档管理端点", 
                        True, 
                        f"获取到 {len(data)} 个文档", 
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "文档管理端点", 
                        False, 
                        "响应格式异常", 
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "文档管理端点", 
                    False, 
                    f"HTTP {response.status_code}", 
                    response_time
                )
                return False
        except Exception as e:
            self.log_test("文档管理端点", False, f"请求失败: {str(e)}")
            return False
    
    def test_api_documentation(self):
        """测试API文档访问"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/docs")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                if "swagger" in response.text.lower() or "openapi" in response.text.lower():
                    self.log_test(
                        "API文档访问", 
                        True, 
                        "Swagger文档可访问", 
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "API文档访问", 
                        False, 
                        "文档内容异常", 
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "API文档访问", 
                    False, 
                    f"HTTP {response.status_code}", 
                    response_time
                )
                return False
        except Exception as e:
            self.log_test("API文档访问", False, f"访问失败: {str(e)}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始Web界面测试...")
        print("=" * 60)
        
        # 基础连接测试
        if not self.test_server_health():
            print("❌ 服务器无法连接，停止测试")
            return False
        
        # 前端测试
        self.test_frontend_access()
        
        # API端点测试
        self.test_health_endpoint()
        self.test_query_endpoint()
        self.test_documents_endpoint()
        self.test_api_documentation()
        
        # 生成测试报告
        self.generate_report()
        
        return True
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 测试报告")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"总测试数: {total_tests}")
        print(f"通过: {passed_tests}")
        print(f"失败: {failed_tests}")
        print(f"成功率: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ 失败的测试:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test_name']}: {result['message']}")
        
        # 性能统计
        response_times = [r["response_time"] for r in self.test_results if r["response_time"] > 0]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            print(f"\n⏱️  响应时间统计:")
            print(f"  平均响应时间: {avg_time:.3f}s")
            print(f"  最大响应时间: {max_time:.3f}s")
        
        print("\n✅ Web界面测试完成!")


def main():
    """主函数"""
    print("InsurIntellect Agent - Web界面测试")
    print("测试服务器: http://localhost:8000")
    print()
    
    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    time.sleep(2)
    
    # 运行测试
    tester = WebInterfaceTest()
    tester.run_all_tests()


if __name__ == "__main__":
    main()