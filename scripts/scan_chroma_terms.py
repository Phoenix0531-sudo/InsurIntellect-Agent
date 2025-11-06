import sys
import re
from app.core.chromadb_manager import chroma_manager

def main():
    limit = 2000
    offset = 0
    terms = [
        # 中文
        "有效期","有效期至","有效至","适用期","适用期至","截止","截至","到期","到期日","到期日期","终止日期","失效日期","结束日期","有效截止",
        "备案日期","报备日期","报批日期","批复日期","印发日期",
        # 英文
        "filing date","filed on","registration date","record filing date","approval date","approved on",
        "valid until","valid through","effective until","expires","expires on","until","expiration","expiration date","end date"
    ]
    counts = {t: 0 for t in terms}
    coll = chroma_manager.get_collection()
    data = coll.get(limit=limit, offset=offset, include=["documents","metadatas"])  # type: ignore
    docs = data.get("documents", [])
    examples = []
    for d in docs:
        txt = (d or "")
        low = txt.lower()
        for t in terms:
            if t.isascii():
                if t in low:
                    counts[t] += 1
            else:
                if t in txt:
                    counts[t] += 1
                    if t == "有效期" and len(examples) < 5:
                        idx = txt.find(t)
                        tail = txt[idx: idx + 200].replace("\n"," ")
                        examples.append(tail)
    print("scanned_chunks:", len(docs))
    print("term_hits:", counts)
    if examples:
        print("examples_of_有效期:")
        for i, ex in enumerate(examples, 1):
            print(f"{i}. {ex}")

if __name__ == "__main__":
    main()
