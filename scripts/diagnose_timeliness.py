#!/usr/bin/env python3
"""
诊断未能提取“时效性/日期”元数据的文件，给出根因与可操作方案。

功能：
- 自动定位最新 backfill 报告，读取其中的未提取/失败样本
- 按文件聚合（优先 file_path，其次 source_file），选取前 N 个问题文件
- 采样若干文本块，检测文本稀疏、OCR迹象、标签词出现与日期正则命中情况
- 输出每个文件的诊断与建议，并生成 JSON/Markdown 报告

用法：
python scripts/diagnose_timeliness.py --limit-files 10 --per-file-chunks 12
python scripts/diagnose_timeliness.py --report reports/backfill_report_20251102_200430.json
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

from app.core.app_logging import setup_logging, get_logger
from app.core.chromadb_manager import chroma_manager


# 关键词（标签近邻检测）：尽量覆盖中文/英文常见表达
EXPIRY_LABELS = [
    "有效期", "有效期限", "有效期至", "有效期到", "到期", "期满", "届满",
    "截止", "截至", "终止", "失效", "废止", "失效日期", "失效时间",
    "valid until", "expiry", "expiration", "expires", "end date"
]

FILING_LABELS = [
    "备案日期", "备案时间", "备案号日期", "登记日期", "登记时间", "注册日期",
    "filing date", "record date", "registration date"
]

# 文本归一化：跨行/空白/分隔增强
def _normalize_for_date(text: str) -> str:
    try:
        s = str(text or "")
        s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
        s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
        s = re.sub(r"(?<=[A-Za-z])\s+(?=[A-Za-z])", "", s)
        return s.strip()
    except Exception:
        return str(text or "")

# 日期正则（中文/英文/ISO）：与 backfill 的覆盖保持一致性（简化版）
DATE_PATTERNS = [
    # ISO: 2024-03-31 / 2024/03/31 / 2024.03.31
    re.compile(r"\b((?:19|20)\d{2})[./-](0?[1-9]|1[0-2])[./-](0?[1-9]|[12]\d|3[01])\b"),
    # 中文（更灵活）：允许空格/可选分隔符，支持“日/号”
    re.compile(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)"),
    # 英文：Month DD, YYYY
    re.compile(r"\b(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?)\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b", re.IGNORECASE),
]


def find_latest_report(report_path: str | None = None) -> Path:
    """选择最新的 backfill 报告 JSON 文件（或使用指定路径）。"""
    if report_path:
        p = Path(report_path)
        if not p.exists():
            raise FileNotFoundError(f"指定报告不存在: {p}")
        return p
    reports_dir = Path("reports")
    candidates = sorted(reports_dir.glob("backfill_report_*.json"), key=lambda x: x.stat().st_ctime, reverse=True)
    if not candidates:
        raise FileNotFoundError("未找到 backfill 报告 JSON 文件")
    return candidates[0]


def load_missing_or_failed_ids(report: Dict[str, Any]) -> List[str]:
    """优先从 verify.missing_ids 读取；若不存在则使用 failed_ids。"""
    ids: List[str] = []
    try:
        verify = report.get("verify") or {}
        ids = list(verify.get("missing_ids") or [])
    except Exception:
        ids = []
    if not ids:
        try:
            ids = list(report.get("failed_ids") or [])
        except Exception:
            ids = []
    return ids


def group_key(md: Dict[str, Any], chunk_id: str) -> str:
    fp = str(md.get("file_path") or "").strip()
    if fp:
        return f"path:{fp}"
    sf = str(md.get("source_file") or "").strip()
    if sf:
        return f"name:{sf}"
    return f"chunk:{chunk_id}"


def text_has_label(text: str, labels: List[str]) -> bool:
    t = _normalize_for_date(text).lower()
    for lb in labels:
        if lb.lower() in t:
            return True
    return False


def text_has_date(text: str) -> bool:
    t = _normalize_for_date(text)
    for pat in DATE_PATTERNS:
        if pat.search(t):
            return True
    return False


def diagnose_groups(collection, group_ids: Dict[str, List[str]], per_file_chunks: int = 12) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for gkey, ids in group_ids.items():
        # 采样部分 chunk 进行诊断
        sample_ids = ids[:per_file_chunks]
        docs: List[str] = []
        metas: List[Dict[str, Any]] = []
        try:
            res = collection.get(ids=sample_ids, include=["documents", "metadatas"])  # type: ignore
            docs = list(res.get("documents") or [])
            metas = list(res.get("metadatas") or [])
        except Exception:
            docs, metas = [], []

        total_len = sum(len(d or "") for d in docs)
        avg_len = (total_len / max(len(docs), 1)) if docs else 0.0
        ocr_ratio = 0.0
        try:
            ocr_hits = sum(1 for m in metas if isinstance(m, dict) and str(m.get("extraction_method") or "") == "ocr")
            ocr_ratio = (ocr_hits / max(len(metas), 1)) if metas else 0.0
        except Exception:
            ocr_ratio = 0.0

        joined = "\n\n".join(docs)
        has_expiry_label = text_has_label(joined, EXPIRY_LABELS)
        has_filing_label = text_has_label(joined, FILING_LABELS)
        has_any_date = text_has_date(joined)

        # 初步规则诊断
        issue = ""
        suggestions: List[str] = []

        # 文本非常稀疏，且 OCR 痕迹少 -> 高概率扫描版图片 PDF
        if avg_len < 30 and ocr_ratio < 0.3:
            issue = "文本稀疏，疑似图片版PDF（未OCR或OCR不足）"
            suggestions.append("对该文件启用OCR重摄取（Tesseract chi_sim），并重新入库")
            suggestions.append("安装Tesseract并在 .env 设置 TESSERACT_CMD，运行 ingest.py 开启OCR")
        # 标签出现但缺少日期 -> 增加邻近窗口与正则覆盖
        elif (has_expiry_label or has_filing_label) and (not has_any_date):
            issue = "标签出现但未匹配到日期"
            suggestions.append("增大标签邻近窗口（如 --neighbor-window 600）")
            suggestions.append("扩展中文日期与分隔符变体正则（例如 年-月-日、空格/无分隔）")
        # 没有标签也没有日期 -> 文本未含时效性线索（或分布在更后页面）
        elif (not has_expiry_label and not has_filing_label) and (not has_any_date):
            issue = "文本未出现时效性线索（标签/日期均缺失）"
            suggestions.append("提高档案官调用的最大内容字符数（--max-content-chars 12000）")
            suggestions.append("从PDF元数据/目录年份兜底，无法准确得到有效期则标记为‘未知/不定期’")
        # 有日期但可能格式未覆盖 -> 扩展正则
        elif has_any_date and not (has_expiry_label or has_filing_label):
            issue = "存在日期但未检测到时效性标签"
            suggestions.append("扩展有效期/备案标签同义词（如：施行期限、实施期限、有效期为等）")
            suggestions.append("允许根据语境句式（as of/effective/published）辅助判断时效性")
        else:
            issue = "无法明确归类，建议增加OCR/扩大窗口并重试"
            suggestions.append("启用OCR + 增加邻近窗口 + 提高最大内容长度后重跑回填")

        # 汇总文件路径/名称展示
        file_path = ""
        source_file = ""
        try:
            for m in metas:
                if isinstance(m, dict):
                    fp = str(m.get("file_path") or "")
                    sf = str(m.get("source_file") or "")
                    if fp and not file_path:
                        file_path = fp
                    if sf and not source_file:
                        source_file = sf
        except Exception:
            pass

        results.append({
            "group_key": gkey,
            "file_path": file_path,
            "source_file": source_file,
            "sample_chunk_count": len(sample_ids),
            "avg_text_len": round(avg_len, 1),
            "ocr_ratio": round(ocr_ratio, 2),
            "has_expiry_label": has_expiry_label,
            "has_filing_label": has_filing_label,
            "has_any_date": has_any_date,
            "issue": issue,
            "suggestions": suggestions,
        })

    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="诊断未能提取时效性的文件")
    parser.add_argument("--report", type=str, default="", help="指定报告JSON路径；为空则自动选择最新")
    parser.add_argument("--limit-files", type=int, default=10, help="最多诊断的文件数量（按缺失块数排序）")
    parser.add_argument("--per-file-chunks", type=int, default=12, help="每个文件采样的块数量")
    parser.add_argument("--output-dir", type=str, default="reports", help="诊断报告输出目录")
    parser.add_argument("--filter-source-file", type=str, default="", help="仅诊断指定 source_file 的文件（例如 sms.pdf）")
    args = parser.parse_args()

    setup_logging(log_level="INFO")
    logger = get_logger(__name__)

    # 选择报告
    rpt_path = find_latest_report(args.report or None)
    logger.info(f"使用报告: {rpt_path}")
    with open(rpt_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    missing_ids = load_missing_or_failed_ids(report)
    if not missing_ids:
        logger.info("报告中不存在 missing_ids / failed_ids，无可诊断样本。")
        return

    logger.info(f"待诊断样本（chunk）数量: {len(missing_ids)}")

    # 查询每个 id 的元数据并按文件聚合
    collection = chroma_manager.get_collection()
    group_map: Dict[str, List[str]] = {}
    for sid in missing_ids:
        try:
            res = collection.get(ids=[sid], include=["metadatas"])  # type: ignore
            metas = res.get("metadatas") or []
            md = metas[0] if metas else {}
        except Exception:
            md = {}
        # 如果指定了 source_file 过滤，则在此处进行筛选
        try:
            if args.filter_source_file and str(md.get("source_file") or "") != args.filter_source_file:
                continue
        except Exception:
            pass
        gk = group_key(md, sid)
        group_map.setdefault(gk, []).append(sid)

    # 按缺失块数排序，选取前 N 文件
    sorted_groups = sorted(group_map.items(), key=lambda kv: len(kv[1]), reverse=True)
    top_groups = dict(sorted_groups[:args.limit_files])
    logger.info(f"选取前 {len(top_groups)} 个问题文件进行诊断")

    results = diagnose_groups(collection, top_groups, per_file_chunks=args.per_file_chunks)

    # 输出报告
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"diagnose_timeliness_{ts}.json"
    md_path = out_dir / f"diagnose_timeliness_{ts}.md"

    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump({
            "source_report": str(rpt_path),
            "analyzed_groups": results,
        }, jf, ensure_ascii=False, indent=2)

    # Markdown 简报
    lines = ["# 时效性诊断报告", f"来源报告: {rpt_path}", ""]
    for item in results:
        lines.append(f"## {item.get('group_key')}\n")
        lines.append(f"- file_path: {item.get('file_path') or '-'}")
        lines.append(f"- source_file: {item.get('source_file') or '-'}")
        lines.append(f"- sample_chunk_count: {item.get('sample_chunk_count')}")
        lines.append(f"- avg_text_len: {item.get('avg_text_len')}\n- ocr_ratio: {item.get('ocr_ratio')}")
        lines.append(f"- has_expiry_label: {item.get('has_expiry_label')}\n- has_filing_label: {item.get('has_filing_label')}\n- has_any_date: {item.get('has_any_date')}")
        lines.append(f"- 诊断: {item.get('issue')}")
        sug = item.get("suggestions") or []
        if sug:
            lines.append("- 建议:")
            for s in sug:
                lines.append(f"  - {s}")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as mf:
        mf.write("\n".join(lines))

    logger.info(f"诊断完成：{json_path} / {md_path}")


if __name__ == "__main__":
    main()
