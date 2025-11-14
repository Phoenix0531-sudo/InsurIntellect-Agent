import asyncio
import time
import json
import httpx

URL = "http://127.0.0.1:8000/api/v1/queries/ask"

QUERIES = [
    "请比较百万医疗险与重疾险在保障范围与理赔上的差异，并给出示例。",
    "如果投保人患有既往症，医疗险是否可以理赔？需要哪些材料？",
    "保单生效后30天内发生的疾病是否属于等待期？条款如何约定？",
    "请解释家庭共享免赔额的适用条件，并比较不同产品。",
    "列出两全保险与年金险的差异点，并分析适用人群。",
]

async def one_request(idx: int):
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        params = {"stream": "true"}
        payload = {
            "question": QUERIES[idx % len(QUERIES)],
            "query_type": "general",
        }
        start_ts = None
        token_events = []
        headers = {"Accept": "text/event-stream"}
        try:
            async with client.stream("POST", URL, params=params, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        evt = line.split(": ", 1)[1].strip()
                    elif line.startswith("data: "):
                        data = line.split(": ", 1)[1].strip()
                        try:
                            obj = json.loads(data)
                        except Exception:
                            obj = {"raw": data}
                        if obj.get("type") == "start":
                            start_ts = time.time()
                            print(f"[req{idx}] start at {start_ts:.3f}")
                        elif obj.get("type") == "token":
                            token = obj.get("content", "")
                            token_events.append((time.time(), token))
                            # 仅打印标记，避免输出过多文本
                            print(f"[req{idx}] token@{time.time():.3f}")
                        elif obj.get("type") == "end":
                            print(f"[req{idx}] end ok, answer_len={len(obj.get('answer',''))}")
                            break
        except Exception as e:
            print(f"[req{idx}] error: {e}")
        return {
            "idx": idx,
            "start_ts": start_ts,
            "token_events": token_events,
        }

async def main():
    tasks = [one_request(i) for i in range(5)]
    results = await asyncio.gather(*tasks)
    starts = [r["start_ts"] for r in results]
    # 检查start事件是否几乎同时（最大间隔<1.0s）
    if all(starts) and (max(starts) - min(starts) < 1.0):
        print(f"[check] start events nearly simultaneous: spread={(max(starts)-min(starts)):.3f}s")
    else:
        print(f"[check] start events NOT simultaneous: starts={starts}")
    # 检查token交错：统计时间线上的请求来源变化次数
    timeline = []
    for r in results:
        for ts, _ in r["token_events"]:
            timeline.append((ts, r["idx"]))
    timeline.sort(key=lambda x: x[0])
    switches = 0
    for i in range(1, len(timeline)):
        if timeline[i][1] != timeline[i-1][1]:
            switches += 1
    print(f"[check] token interleaving switches={switches}, total_tokens={len(timeline)}")

if __name__ == "__main__":
    asyncio.run(main())
