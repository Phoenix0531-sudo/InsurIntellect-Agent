import json
import sys
import requests


def main():
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "测试保单理赔流程有哪些材料？"
    )
    url = "http://127.0.0.1:8000/api/v1/queries/ask"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    payload = {
        "question": question,
        "stream": True,
    }

    print(f"POST {url} (SSE) ...")
    try:
        with requests.post(url, headers=headers, data=json.dumps(payload), stream=True) as r:
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                # 仅打印关键事件与数据行
                if line.startswith("event:") or line.startswith("data:"):
                    print(line)
    except requests.RequestException as e:
        print(f"SSE 请求失败: {e}")


if __name__ == "__main__":
    main()

