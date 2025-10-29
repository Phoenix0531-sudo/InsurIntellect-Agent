import sys
import re
import json


def scan_text(text, page_index):
    text = (text or "").replace("\u3000", " ").replace("\t", " ")
    results = []

    # 直接匹配常见格式
    direct_patterns = {
        "免赔额": r"(免赔额|起付线)[：: ]?([0-9.,]+\s*(?:元|人民币|万元)?)",
        "报销比例": r"(报销比例|赔付比例)[：: ]?([0-9]{1,3}\s*%)",
        "年度上限": r"(年度上限|年度限额|年度最高赔付|最高保额|赔付上限)[：: ]?([0-9.,]+\s*(?:元|人民币|万元|百万元)?)",
    }
    for term, pat in direct_patterns.items():
        for m in re.finditer(pat, text):
            snippet = text[max(0, m.start() - 60) : m.end() + 60].replace("\n", " ")
            results.append(
                {
                    "term": term,
                    "page": page_index,
                    "match": m.group(0),
                    "value": (m.group(2) if m.lastindex and m.lastindex >= 2 else None),
                    "snippet": snippet,
                }
            )

    # 近邻匹配（关键词周围抓取数值或百分比）
    keywords = {
        "免赔额": ["免赔额", "起付线", "免赔"],
        "报销比例": ["报销比例", "赔付比例", "比例"],
        "年度上限": ["年度上限", "年度限额", "年度最高赔付", "最高保额", "赔付上限", "封顶线", "年度保额"],
    }
    number_pat = re.compile(r"([0-9]{1,3}\s*%)|([0-9.,]+\s*(?:元|人民币|万元|百万元))")
    window = 80
    for term, keys in keywords.items():
        for key in keys:
            for m in re.finditer(re.escape(key), text):
                start = max(0, m.start() - window)
                end = min(len(text), m.end() + window)
                segment = text[start:end]
                for nm in number_pat.finditer(segment):
                    snippet = segment[max(0, nm.start()-40): nm.end()+40].replace("\n", " ")
                    value = nm.group(1) or nm.group(2)
                    results.append({
                        "term": term,
                        "page": page_index,
                        "match": f"{key} … {value}",
                        "value": value,
                        "snippet": snippet,
                    })

    return results


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing_arg", "detail": "Usage: python scripts/search_pdf_terms.py <pdf_path>"}, ensure_ascii=False))
        return

    pdf_path = sys.argv[1]
    results = []

    # Try pdfplumber first
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if text:
                    results.extend(scan_text(text, i))
    except Exception as e:
        results.append({"error": "pdfplumber_failed", "detail": str(e)})

    # Fallback to PyPDF2 if nothing found
    if not results:
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(pdf_path)
            for i, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if text:
                    results.extend(scan_text(text, i))
        except Exception as e2:
            results.append({"error": "pypdf2_failed", "detail": str(e2)})

    print(json.dumps(results[:50], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

