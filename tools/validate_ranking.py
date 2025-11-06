#!/usr/bin/env python3
"""
排序验证脚本：validate_ranking.py

功能：
- 加载测试用例（tools/ranking_test_cases.json）
- 调用 RAG 工作流以获取候选与动态排序结果（_dynamic_ranking）
- 对比验证（位置容差±2），生成 HTML 报告
- 支持网络错误自动重试与结果通知（Slack/Email）

环境变量：
- SLACK_WEBHOOK_URL（可选）
- SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL（可选）
"""

import os
import sys
import json
import time
import smtplib
from email.mime.text import MIMEText
from typing import List, Dict, Any, Tuple
from datetime import datetime

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.app_logging import setup_logging, get_logger
from app.core.rag_workflow import InsurIntellectAgent


def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return datetime(1970, 1, 1)


def is_recent(metadata: Dict[str, Any], recent_days: int) -> bool:
    candidates = [metadata.get("effective_date"), metadata.get("publish_date"), metadata.get("last_updated_date")]
    for d in candidates:
        if d and str(d).strip() and str(d).strip() != "未知":
            dt = parse_date(str(d).strip())
            return (datetime.now() - dt).days <= recent_days
    return False


def is_expired(metadata: Dict[str, Any], threshold_days: int) -> bool:
    # 简化定义：若有效/更新日期距今超过阈值视为过期
    candidates = [metadata.get("effective_date"), metadata.get("last_updated_date"), metadata.get("publish_date")]
    best = None
    for d in candidates:
        if d and str(d).strip() and str(d).strip() != "未知":
            dt = parse_date(str(d).strip())
            if best is None or dt > best:
                best = dt
    if best is None:
        return True
    return (datetime.now() - best).days >= threshold_days


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def get_selected_docs(agent: InsurIntellectAgent, query: str) -> Tuple[List[Any], str]:
    """完整管线：重写查询 -> 检索 -> 监管重排 -> 首席评审员。返回候选和重写后的查询。"""
    architect_result = agent.run_query_architect(query)
    # 安全回退：若重写失败或返回空/标记性失败文本，则使用原始查询
    rewritten_candidate = architect_result.get("rewritten_query", "")
    if not rewritten_candidate:
        rewritten = query
    else:
        text = str(rewritten_candidate).strip()
        if not text or ("解析失败" in text) or ("parse failed" in text.lower()) or ("failed" in text.lower()):
            rewritten = query
        else:
            rewritten = text
    retrieved = agent.retriever.invoke(rewritten)
    reranked = agent._regulatory_rerank(query, retrieved)
    selected = agent.run_lead_reviewer(query, reranked)
    return selected, rewritten


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def run_dynamic_ranking(agent: InsurIntellectAgent, docs: List[Any], rewritten_query: str) -> List[Any]:
    return agent._dynamic_ranking(docs, rewritten_query)


def run_baseline_ranking(agent: InsurIntellectAgent, docs: List[Any], rewritten_query: str) -> List[Any]:
    """基线排序：禁用监管加分以衡量提升幅度。"""
    orig = agent._is_query_regulatory
    try:
        agent._is_query_regulatory = lambda q: False
        return agent._dynamic_ranking(docs, rewritten_query)
    finally:
        agent._is_query_regulatory = orig


def index_map(docs: List[Any]) -> Dict[str, int]:
    m = {}
    for i, d in enumerate(docs):
        did = str(d.metadata.get("doc_id", d.metadata.get("source_id", d.metadata.get("id", f"idx-{i}"))))
        m[did] = i
    return m


def notify_slack(webhook_url: str, text: str) -> None:
    try:
        import requests
        requests.post(webhook_url, json={"text": text}, timeout=10)
    except Exception:
        get_logger().warning("Slack 通知失败")


def notify_email(smtp_server: str, smtp_port: int, user: str, password: str, to_email: str, subject: str, body_html: str) -> None:
    try:
        msg = MIMEText(body_html, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_email
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_email], msg.as_string())
    except Exception:
        get_logger().warning("邮件通知失败")


def validate_new_document_recall(agent: InsurIntellectAgent, case: Dict[str, Any], tol: int = 2) -> Tuple[bool, Dict[str, Any]]:
    selected, rewritten = get_selected_docs(agent, case["query"])  # 重试包装
    start = time.perf_counter()
    ranked = run_dynamic_ranking(agent, selected, rewritten)
    elapsed = round(time.perf_counter() - start, 3)
    top_k = case.get("top_k", 3) + tol
    ok = any(is_recent(d.metadata or {}, case.get("recent_days", 30)) for d in ranked[:top_k])
    return ok, {"elapsed": elapsed, "top_checked": top_k, "selected": len(selected), "ranked": len(ranked)}


def validate_expired_suppression(agent: InsurIntellectAgent, case: Dict[str, Any], tol: int = 2) -> Tuple[bool, Dict[str, Any]]:
    selected, rewritten = get_selected_docs(agent, case["query"])  # 重试包装
    start = time.perf_counter()
    ranked = run_dynamic_ranking(agent, selected, rewritten)
    elapsed = round(time.perf_counter() - start, 3)
    max_rank = case.get("max_rank_for_expired", 10) - tol  # 给出容差
    ok = True
    for d in ranked:
        if is_expired(d.metadata or {}, case.get("expired_threshold_days", 365)):
            pos = ranked.index(d)
            if pos <= max_rank:
                ok = False
                break
    return ok, {"elapsed": elapsed, "selected": len(selected), "ranked": len(ranked), "max_rank_for_expired": max_rank}


def validate_regulatory_alignment(agent: InsurIntellectAgent, case: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    selected, rewritten = get_selected_docs(agent, case["query"])  # 重试包装
    start = time.perf_counter()
    ranked = run_dynamic_ranking(agent, selected, rewritten)
    elapsed = round(time.perf_counter() - start, 3)

    baseline = run_baseline_ranking(agent, selected, rewritten)
    idx_new = index_map(ranked)
    idx_base = index_map(baseline)

    # 识别潜在受影响产品文档：AI判定与监管查询高度关联，且非监管文件
    affected_positions: List[int] = []
    for d in ranked:
        try:
            doc_type = (d.metadata or {}).get("document_type", "")
            if "监管" in doc_type:
                continue
            if agent._is_doc_related_to_regulatory_query(d, case["query"]):
                did = str(d.metadata.get("doc_id", d.metadata.get("source_id", d.metadata.get("id", "unknown"))))
                if did in idx_base and did in idx_new:
                    gain = idx_base[did] - idx_new[did]
                    affected_positions.append(gain)
        except Exception:
            continue

    min_gain_required = case.get("min_rank_gain", 5)
    ok = any(g >= min_gain_required for g in affected_positions) if affected_positions else False
    return ok, {"elapsed": elapsed, "affected_count": len(affected_positions), "gains": affected_positions}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="动态排序验证脚本")
    parser.add_argument("--cases", type=str, default="tools/ranking_test_cases.json", help="测试用例配置文件路径")
    parser.add_argument("--report-dir", type=str, default=os.environ.get("REPORT_DIR", "reports"), help="报告输出目录")
    parser.add_argument("--log-level", type=str, default=os.environ.get("LOG_LEVEL", "INFO"), help="日志级别")
    args = parser.parse_args()

    os.makedirs(args.report_dir, exist_ok=True)
    logger = setup_logging(log_level=args.log_level, log_file=os.path.join(args.report_dir, "ranking_validate.log"))
    logger.info("开始执行排序验证")

    # 加载测试用例
    try:
        with open(args.cases, "r", encoding="utf-8") as f:
            cases = json.load(f)
    except Exception as e:
        logger.error(f"加载测试用例失败: {e}")
        sys.exit(2)

    agent = InsurIntellectAgent()

    results: Dict[str, Any] = {"summary": {}, "details": []}
    total = 0
    passed = 0

    # 新文档召回
    for case in cases.get("new_document_recall", []):
        total += 1
        ok, info = validate_new_document_recall(agent, case, tol=2)
        results["details"].append({"category": "new_document_recall", "id": case.get("id"), "query": case.get("query"), "passed": ok, "info": info})
        if ok:
            passed += 1

    # 过期文档抑制
    for case in cases.get("expired_document_suppression", []):
        total += 1
        ok, info = validate_expired_suppression(agent, case, tol=2)
        results["details"].append({"category": "expired_document_suppression", "id": case.get("id"), "query": case.get("query"), "passed": ok, "info": info})
        if ok:
            passed += 1

    # 监管对齐
    for case in cases.get("regulatory_alignment", []):
        total += 1
        ok, info = validate_regulatory_alignment(agent, case)
        results["details"].append({"category": "regulatory_alignment", "id": case.get("id"), "query": case.get("query"), "passed": ok, "info": info})
        if ok:
            passed += 1

    results["summary"] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_ratio": round(passed / max(total, 1), 4)
    }

    # 生成HTML报告
    base = os.path.join(args.report_dir, f"ranking_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='utf-8'><title>Ranking Validation Report</title>")
        f.write("<style>body{font-family:Arial,Helvetica,sans-serif} table{border-collapse:collapse} td,th{border:1px solid #ddd;padding:8px}</style>")
        f.write("</head><body>")
        f.write("<h2>动态排序验证报告</h2>")
        f.write(f"<p>汇总：{json.dumps(results['summary'], ensure_ascii=False)}</p>")
        f.write("<table><tr><th>类别</th><th>ID</th><th>查询</th><th>通过</th><th>详情</th></tr>")
        for d in results["details"]:
            f.write(f"<tr><td>{d['category']}</td><td>{d['id']}</td><td>{d['query']}</td><td>{'✅' if d['passed'] else '❌'}</td><td><pre>{json.dumps(d['info'], ensure_ascii=False, indent=2)}</pre></td></tr>")
        f.write("</table>")
        f.write("</body></html>")

    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"验证报告已生成：{base}.html / {base}.json")

    # 结果通知（可选）
    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if slack_url:
        notify_slack(slack_url, f"排序验证完成：通过 {passed}/{total}，报告：{base}.html")

    smtp_server = os.environ.get("SMTP_SERVER", "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
    notify_email_addr = os.environ.get("NOTIFY_EMAIL", "").strip()
    if smtp_server and smtp_user and smtp_password and notify_email_addr:
        with open(base + ".html", "r", encoding="utf-8") as f:
            html = f.read()
        notify_email(smtp_server, smtp_port, smtp_user, smtp_password, notify_email_addr, "排序验证完成", html)


if __name__ == "__main__":
    main()
