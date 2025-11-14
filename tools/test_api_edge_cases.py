#!/usr/bin/env python3
"""
异常输入处理测试：验证服务对于异常/极端输入的健壮性。

测试内容：
 - 空问题
 - 超长问题
 - 非法 JSON 字段
 - 错误的类型与缺失字段
 - 随机二进制噪声
"""

import json
import requests

BASE_URL = "http://127.0.0.1:8000"
ASK_URL = f"{BASE_URL}/api/v1/queries/ask"
HDRS = {"Content-Type": "application/json"}


def case(name, payload):
    print(f"\n[CASE] {name}")
    try:
        r = requests.post(ASK_URL, headers=HDRS, data=json.dumps(payload), timeout=15)
        print("status:", r.status_code)
        try:
            print("json:", r.json())
        except Exception:
            print("text:", r.text[:500])
    except Exception as e:
        print("error:", e)


def main():
    # 空问题
    case("empty question", {"question": "", "stream": False})

    # 超长问题
    long_q = "保险条款" * 10000
    case("very long question", {"question": long_q, "stream": False})

    # 非法字段
    case("invalid field types", {"question": 12345, "max_chunks": "abc", "stream": "no"})

    # 缺失必填字段
    case("missing question", {"max_chunks": 3, "stream": False})

    # 噪声与控制字符
    noise = "\x00\x01\x02随机噪声" * 100
    case("binary noise", {"question": noise, "stream": False})


if __name__ == "__main__":
    main()

