#!/usr/bin/env python3
"""
一次性脚本：文档日期元数据补全（Backfill）

功能流程：
- 数据库扫描（ChromaDB集合）识别缺失日期元数据的文档
- 通过“数字档案官”AI接口补全日期元数据（含重试与指数退避）
- 批量原子更新（尽可能保证每批次要么全部成功、要么全部失败）
- 执行后验证并生成报告（成功率、失败案例、处理数量）

环境变量：
- ARCHIVER_API_URL：数字档案官 API 端点（必需）
- ARCHIVER_API_KEY：数字档案官 API 密钥（必需）
- REPORT_DIR：报告输出目录（默认：reports）

使用示例：
python scripts/backfill_metadata.py --batch-size 200
"""

import os
import sys
import json
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple
from datetime import datetime

import requests
from requests.exceptions import RequestException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from app.core.app_logging import setup_logging, get_logger
from app.core.chromadb_manager import chroma_manager
from dotenv import load_dotenv
from app.core.database import db_manager
from app.models.database_models import Document
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


# 关键时间字段定义（至少有一个即可视为已写入日期）
# 核心完整度以 publish/last_updated/effective 任意存在为准；扩展可选字段用于更全面统计
REQUIRED_DATE_FIELDS = ["publish_date", "last_updated_date", "effective_date"]
OPTIONAL_DATE_FIELDS = ["expiry_date", "filing_date"]

# 启发式标签邻近窗口（字符数），用于标签后/前邻近区域的日期抓取
# 可通过环境变量 BACKFILL_LABEL_WINDOW 或命令行参数 --neighbor-window 配置
EXTRACT_LABEL_WINDOW = int(os.environ.get("BACKFILL_LABEL_WINDOW", "300"))

# 文本归一化：跨行/空白/分隔增强，用于日期/标签识别
def _normalize_for_date(text: str) -> str:
    try:
        s = str(text or "")
        # 统一换行与制表符为空格
        s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        # 压缩连续空白为单个空格
        s = re.sub(r"\s+", " ", s)
        # 去除数字之间的空格（例如 OCR 产生的 "2 0 2 4" -> "2024"）
        s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
        # 去除连续中文字符之间的空格（例如 "有 效 期" -> "有效期"）
        s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
        # 去除连续英文字母之间的空格（例如 "E x p i r y" -> "Expiry"）
        s = re.sub(r"(?<=[A-Za-z])\s+(?=[A-Za-z])", "", s)
        # 将中文数字形式统一为阿拉伯数字（适配 二〇二五年、一月、十日 等）
        CN_NUM = {
            "零": "0", "〇": "0", "○": "0", "Ｏ": "0",
            "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
            "六": "6", "七": "7", "八": "8", "九": "9",
            "壹": "1", "贰": "2", "叁": "3", "肆": "4", "伍": "5",
            "陆": "6", "柒": "7", "捌": "8", "玖": "9",
        }
        def _cn_to_int_token(tok: str) -> str:
            # 简化规则：仅对由上述字符组成的连续片段进行逐字符映射
            out = "".join(CN_NUM.get(ch, ch) for ch in tok)
            return out
        # 年份：如 二〇二五年 -> 2025年
        s = re.sub(r"([零〇○Ｏ一二三四五六七八九壹贰叁肆伍陆柒捌玖]{2,6})年",
                   lambda m: f"{_cn_to_int_token(m.group(1))}年", s)
        # 月份：如 十一月、一月 -> 11月/1月（保守：仅逐字符映射，不做十/二十组合进位）
        s = re.sub(r"([零〇○Ｏ一二三四五六七八九壹贰叁肆伍陆柒捌玖]{1,2})月",
                   lambda m: f"{_cn_to_int_token(m.group(1))}月", s)
        # 日期：如 二十五日、十日 -> 25日/10日（同上，逐字符映射）
        s = re.sub(r"([零〇○Ｏ一二三四五六七八九壹贰叁肆伍陆柒捌玖]{1,2})日",
                   lambda m: f"{_cn_to_int_token(m.group(1))}日", s)
        # 统一点号日期为短横：2025.1.2 / 2025.01.02 -> 2025-01-02
        s = re.sub(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", s)
        # 统一中文分隔：2025年1月2日 -> 2025-01-02（仅在模式完整时生效）
        s = re.sub(r"(\d{4})年(\d{1,2})月(\d{1,2})日", lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", s)
        return s.strip()
    except Exception:
        return str(text or "")


def is_missing_date_metadata(metadata: Dict[str, Any]) -> bool:
    """若三个日期字段都为空/未知，视为缺失；任意一个存在则视为已写入。"""
    if not metadata:
        return True
    for k in REQUIRED_DATE_FIELDS:
        v = metadata.get(k)
        if v is not None:
            sv = str(v).strip()
            if sv and sv != "未知":
                return False
    return True


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
       retry=retry_if_exception_type(RequestException))
def call_archiver_api(api_url: str, api_key: str, doc_id: str, content: str, existing_metadata: Dict[str, Any], api_model: str = "") -> Dict[str, Any]:
    """调用“数字档案官”AI接口，返回补全的日期元数据。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "doc_id": doc_id,
        "content": content,
        "existing_metadata": existing_metadata,
        "request_fields": REQUIRED_DATE_FIELDS + OPTIONAL_DATE_FIELDS,
    }
    if api_model:
        payload["model"] = api_model
    resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # 期望返回类似：{"publish_date": "YYYY-MM-DD", "last_updated_date": "YYYY-MM-DD", "effective_date": "YYYY-MM-DD", "expiry_date": "YYYY-MM-DD", "filing_date": "YYYY-MM-DD"}
    return data or {}


def fetch_all_documents(batch_size: int = 500, where: Dict[str, Any] | None = None, max_docs: int | None = None) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    """分页拉取集合中的全部或部分文档 IDs、内容与元数据。支持 where 过滤与最大数量限制。"""
    logger = get_logger()
    collection = chroma_manager.get_collection()
    logger.debug("准备统计 Chroma 集合总数")
    total = collection.count()
    logger.debug(f"Chroma 集合总数: {total}")
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []
    offset = 0
    while offset < total:
        limit = min(batch_size, total - offset)
        logger.debug(f"分页拉取: offset={offset}, limit={limit}")
        # 注意：Chroma 的 include 不支持 'ids'，ids 默认返回
        if where:
            batch = collection.get(limit=limit, offset=offset, include=["metadatas", "documents"], where=where)  # type: ignore
        else:
            batch = collection.get(limit=limit, offset=offset, include=["metadatas", "documents"])  # type: ignore
        ids.extend(batch.get("ids", []))
        docs.extend(batch.get("documents", []))
        metas.extend(batch.get("metadatas", []))
        logger.debug(f"分页完成: 累计 ids={len(ids)}, docs={len(docs)}, metas={len(metas)}")
        offset += batch_size
        if max_docs is not None and len(ids) >= max_docs:
            ids = ids[:max_docs]
            docs = docs[:max_docs]
            metas = metas[:max_docs]
            break
    return ids, docs, metas


def batch_update_dates(update_items: List[Tuple[str, Dict[str, Any]]], salvage_on_batch_failure: bool = False) -> Tuple[int, List[str]]:
    """批量更新日期元数据，返回成功数与失败ID列表。"""
    collection = chroma_manager.get_collection()
    success = 0
    failed: List[str] = []
    if not update_items:
        return success, failed
    # 拆分批次，保证每批次规模较小以降低失败风险
    BATCH = 100
    for i in range(0, len(update_items), BATCH):
        sub = update_items[i:i+BATCH]
        ids = [sid for sid, _ in sub]
        metadatas = [md for _, md in sub]
        try:
            # Chroma 的 update 在一个调用内是原子性的（要么所有 id 更新成功，要么抛异常）
            collection.update(ids=ids, metadatas=metadatas)  # type: ignore
            success += len(sub)
        except Exception as e:
            # 记录失败，但不中断总流程；可选逐条回退以尽量挽救部分更新
            if salvage_on_batch_failure:
                for (sid, md) in sub:
                    try:
                        collection.update(ids=[sid], metadatas=[md])  # type: ignore
                        success += 1
                    except Exception:
                        failed.append(sid)
            else:
                failed.extend(ids)
    return success, failed


def verify_database_integrity() -> Dict[str, Any]:
    """验证补全后数据库完整性，统计缺失与完整比例。"""
    ids, docs, metas = fetch_all_documents(batch_size=1000)
    total = len(ids)
    missing = 0
    missing_ids: List[str] = []
    for did, md in zip(ids, metas):
        if is_missing_date_metadata(md):
            missing += 1
            missing_ids.append(did)
    return {
        "total_documents": total,
        "missing_after_backfill": missing,
        "missing_ids": missing_ids,
        "complete_ratio": round((total - missing) / max(total, 1), 4),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="一次性：日期元数据补全脚本")
    parser.add_argument("--batch-size", type=int, default=500, help="分页读取的批大小")
    parser.add_argument("--report-dir", type=str, default=os.environ.get("REPORT_DIR", "reports"), help="报告输出目录")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("BACKFILL_WORKERS", "8")), help="并发调用档案官的工作线程数")
    parser.add_argument("--max-content-chars", type=int, default=int(os.environ.get("BACKFILL_MAX_CONTENT", "8000")), help="每条文档传给档案官的内容最大字符数（避免超长导致慢或失败）")
    parser.add_argument("--fallback", action="store_true", help="强制启用本地启发式日期抽取回退模式（不调用档案官API）")
    parser.add_argument("--where-json", type=str, default="", help="可选：对集合进行 where 过滤的JSON，如 {\"page_number\":1}")
    parser.add_argument("--max-docs", type=int, default=0, help="可选：仅处理前 N 条文档用于抽样验证")
    parser.add_argument("--retry-failed-from", type=str, default="", help="仅对指定报告中的 failed_ids 进行增量重试")
    parser.add_argument("--api-model", type=str, default=os.environ.get("ARCHIVER_API_MODEL", ""), help="可选：档案官调用使用的模型或配置标识")
    parser.add_argument("--scan-pages", type=int, default=int(os.environ.get("BACKFILL_SCAN_PAGES", "3")), help="启发式抽取时聚合前 N 页文本")
    parser.add_argument("--salvage-on-batch-failure", action="store_true", help="批量更新失败时逐条回退补救")
    parser.add_argument("--neighbor-window", type=int, default=int(os.environ.get("BACKFILL_LABEL_WINDOW", "300")), help="标签邻近窗口字符数（用于标签后/前的日期扫描），默认300")
    parser.add_argument("--enable-hybrid", action="store_true", help="启用规则与学习混合器（默认通过环境变量开启）")
    parser.add_argument("--enable-version-chain", action="store_true", help="启用版本链对齐推断（默认通过环境变量开启）")
    parser.add_argument("--only-missing", action="store_true", help="仅处理存在日期缺失的文档（按文件聚合），但保留该文件内所有块以便利用已有日期统一回填")
    parser.add_argument("--auto-strategy", action="store_true", help="按文档类型自动应用分策略（publish 现有但缺其它、无日期信号组）")
    args = parser.parse_args()

    # 加载 .env，以便读取 ARCHIVER_API_URL / ARCHIVER_API_KEY
    try:
        load_dotenv()
    except Exception:
        pass

    logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"), log_file=os.path.join(args.report_dir, "backfill.log"))
    logger.info("开始执行元数据补全任务")

    # 应用邻近窗口配置到全局启发式设置
    try:
        global EXTRACT_LABEL_WINDOW
        EXTRACT_LABEL_WINDOW = max(50, int(getattr(args, "neighbor_window", EXTRACT_LABEL_WINDOW)))
        logger.info(f"启发式标签邻近窗口: {EXTRACT_LABEL_WINDOW} 字符")
    except Exception:
        pass

    api_url = os.environ.get("ARCHIVER_API_URL", "").strip()
    api_key = os.environ.get("ARCHIVER_API_KEY", "").strip()
    api_model = (args.api_model or os.environ.get("ARCHIVER_API_MODEL", "")).strip()
    env_force_fallback = os.environ.get("BACKFILL_FORCE_FALLBACK", "").strip().lower() in {"1", "true", "yes"}
    fallback_mode = bool(args.fallback) or env_force_fallback
    enable_hybrid = (os.environ.get("BACKFILL_ENABLE_HYBRID", "1").strip().lower() in {"1", "true", "yes"}) or bool(getattr(args, "enable_hybrid", False))
    enable_version_chain = (os.environ.get("BACKFILL_ENABLE_VERSION_CHAIN", "1").strip().lower() in {"1", "true", "yes"}) or bool(getattr(args, "enable_version_chain", False))
    if fallback_mode:
        logger.warning("强制使用本地启发式日期抽取回退模式（不调用档案官API）")
    else:
        if not api_url or not api_key:
            logger.warning("未配置 ARCHIVER_API_URL/ARCHIVER_API_KEY，将启用本地启发式日期抽取回退模式")
            fallback_mode = True
        else:
            logger.info(f"使用档案官网关: {api_url}")

    os.makedirs(args.report_dir, exist_ok=True)

    start_ts = time.perf_counter()
    logger.info("开始扫描 Chroma 集合...")
    where = None
    if args.where_json and args.where_json.strip():
        try:
            where = json.loads(args.where_json.strip())
            logger.info(f"应用 where 过滤: {where}")
        except Exception:
            logger.warning("--where-json 解析失败，忽略过滤")
    max_docs = args.max_docs if args.max_docs and args.max_docs > 0 else None
    ids, docs, metas = fetch_all_documents(batch_size=args.batch_size, where=where, max_docs=max_docs)
    logger.info(f"扫描到 {len(ids)} 条文档记录")

    # 增量重试：若提供报告文件，则仅筛选其中的失败ID重试
    if args.retry_failed_from and args.retry_failed_from.strip():
        try:
            with open(args.retry_failed_from.strip(), "r", encoding="utf-8") as rf:
                rep = json.load(rf)
            failed_ids: List[str] = list(rep.get("failed_ids", []))
            failed_set = set(str(x) for x in failed_ids)
            if failed_set:
                logger.info(f"启用增量重试：从报告加载失败ID {len(failed_set)} 条")
                filt_ids: List[str] = []
                filt_docs: List[str] = []
                filt_metas: List[Dict[str, Any]] = []
                for did, doc, md in zip(ids, docs, metas):
                    if str(did) in failed_set:
                        filt_ids.append(did)
                        filt_docs.append(doc)
                        filt_metas.append(md)
                ids, docs, metas = filt_ids, filt_docs, filt_metas
                logger.info(f"筛选后待处理失败样本：{len(ids)} 条")
            else:
                logger.warning("报告中未发现 failed_ids 字段或为空，跳过增量重试筛选")
        except Exception:
            logger.warning("--retry-failed-from 解析或读取失败，跳过增量重试筛选")

    # 按文档聚合键聚合：优先使用 document_id，其次 file_path，最后 source_file
    def _group_key(md: Dict[str, Any], chunk_id: str) -> str:
        doc_id_val = md.get("document_id")
        if doc_id_val is not None and str(doc_id_val).strip():
            return f"id:{str(doc_id_val).strip()}"
        fp = str(md.get("file_path") or "").strip()
        if fp:
            return f"path:{fp}"
        sf = str(md.get("source_file") or "").strip()
        if sf:
            return f"name:{sf}"
        # 极端情况：缺少所有标识字段，则退化为按块ID分组（单块）
        return f"chunk:{chunk_id}"

    groups: Dict[str, List[Tuple[str, Dict[str, Any], str]]] = {}
    for did, md, content in zip(ids, metas, docs):
        key = _group_key(md or {}, did)
        groups.setdefault(key, []).append((did, md or {}, content or ""))

    # 初始文档键集合
    doc_keys = list(groups.keys())
    logger.info(f"按文件聚合：共 {len(doc_keys)} 个文档")

    # 仅处理缺失文档：筛选至少存在一个缺失块的文档键，但保留文档内所有块用于统一回填
    if getattr(args, "only_missing", False):
        filtered_keys: List[str] = []
        for k, items in groups.items():
            try:
                if any(is_missing_date_metadata(md) for _, md, _ in items):
                    filtered_keys.append(k)
            except Exception:
                # 保险起见，异常时不筛掉该文档
                filtered_keys.append(k)
        before = len(doc_keys)
        doc_keys = filtered_keys
        logger.info(f"仅处理缺失文档：从 {before} 筛至 {len(doc_keys)} 个文档")

    updates: List[Tuple[str, Dict[str, Any]]] = []
    failures: List[str] = []
    source_stats: Dict[str, int] = {}
    weak_signal_doc_keys: List[str] = []
    field_update_counts: Dict[str, int] = {"effective_date": 0, "last_updated_date": 0, "publish_date": 0, "expiry_date": 0, "filing_date": 0}
    strategy_stats: Dict[str, int] = {"baseline": 0, "publish_missing_others": 0, "no_signal": 0}
    logger.info(f"开始批量补全：按文件处理 {len(doc_keys)} 个文档，workers={args.workers}")

    def _extract_date_candidates(text: str, md: Dict[str, Any]) -> List[str]:
        """从正文与文件名/路径中提取日期候选，统一为 YYYY-MM-DD。按时间倒序返回。"""
        MONTHS = {
            # 完整英文月份
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            # 英文缩写（含常见变体）
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        LABELS = [
            "effective date", "effective", "policy effective", "policy effective date",
            "published", "publish date", "publication date",
            "last updated", "last revised", "revision date", "updated",
            "issue date", "date of issue",
            "as of", "as at",
            # 中文标签
            "生效日期", "生效", "政策生效", "发布日期", "发布", "发布时间", "更新时间", "最后更新",
            "修订日期", "版本日期", "印发日期", "印发时间", "实施日期", "实施时间",
            # 中文语义锚点变体
            "发布于", "印发于", "更新于", "修订于", "生效于",
        ]
        # 有效期/截至（专用于 expiry/valid_until 提取）
        EXPIRY_LABELS = [
            # 英文常见表达
            "expiry", "expiry date", "expires", "expires on", "valid until", "valid thru", "until",
            "expiration", "expiration date", "end date", "valid through", "effective until",
            # 中文常见表达
            "有效期", "有效期至", "有效至", "适用期", "适用期至", "截止", "截至", "至",
            "到期", "到期日", "到期日期", "终止日期", "失效日期", "结束日期", "有效截止",
        ]
        # 备案日期/备案版本（专用于 filing 提取）
        FILING_LABELS = [
            # 英文常见表达
            "filing date", "filed on", "registration date", "record filing date", "approval date", "approved on",
            # 中文常见表达
            "备案日期", "备案时间", "备案版本", "报备日期", "报备时间", "报批日期", "批复日期", "印发日期", "发布印发",
        ]

        # 季度映射（以季度首月作为推断）
        QMAP_EN = {"Q1": 1, "Q2": 4, "Q3": 7, "Q4": 10}
        QMAP_ZH = {"一": 1, "二": 4, "三": 7, "四": 10}

        def _norm(y: int | str, m: int | str, d: int | str | None) -> str:
            yy = int(y)
            mm = int(m)
            dd = int(d) if d is not None else 1
            return f"{yy:04d}-{mm:02d}-{dd:02d}"

        candidates: List[str] = []
        buf = _normalize_for_date(" ".join([
            text or "",
            str(md.get("source_file") or ""),
            str(md.get("file_path") or ""),
            str(md.get("document_title") or ""),
        ]))

        # ISO: YYYY-MM-DD
        for m in re.finditer(r"\b((?:19|20)\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))

        # Slash: YYYY/MM/DD
        for m in re.finditer(r"\b((?:19|20)\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))

        # Chinese: YYYY年MM月DD日（标准）
        for m in re.finditer(r"((?:19|20)\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
        # Chinese variants: 支持空格与分隔符（- · /）
        for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))

        # Chinese: YYYY年MM月（默认1号）
        for m in re.finditer(r"((?:19|20)\d{2})年(0?[1-9]|1[0-2])月", buf):
            candidates.append(_norm(m.group(1), m.group(2), None))
        # Chinese variants: 年月支持空格与分隔符（默认1号）
        for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月", buf):
            candidates.append(_norm(m.group(1), m.group(2), None))

        # Chinese normative doc numbers with bracketed year, e.g., 〔2021〕XX号 / (2022)XX
        for m in re.finditer(r"(?:\(|（|\[|〔|【)\s*((?:19|20)\d{2})\s*(?:\)|）|\]|〕|】)\s*[^\n]{0,30}?号", buf):
            candidates.append(_norm(m.group(1), 1, None))
        # Bracketed year without '号', still treat as year-only
        for m in re.finditer(r"(?:\(|（|\[|〔|【)\s*((?:19|20)\d{2})\s*(?:\)|）|\]|〕|】)", buf):
            candidates.append(_norm(m.group(1), 1, None))

        # Chinese numerals: 二〇二四年七月十五日 / 二零二一年七月 / 二〇二四年
        try:
            CN_MAP = {"零": "0", "〇": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
            def _cn_year_to_int(ycn: str) -> int | None:
                y = "".join(CN_MAP.get(ch, "") for ch in ycn)
                return int(y) if len(y) == 4 and y.isdigit() else None
            def _cn_num_to_int(s: str | None) -> int | None:
                if not s:
                    return None
                s = s.strip()
                if s == "十":
                    return 10
                # 处理 十一、十二 等
                if s.startswith("十"):
                    tail = CN_MAP.get(s[1:], "0") if len(s) > 1 else "0"
                    return 10 + int(tail)
                # 处理 二十、二十一 等
                if "十" in s:
                    parts = s.split("十")
                    tens = int(CN_MAP.get(parts[0], "0")) if parts[0] else 1
                    ones = int(CN_MAP.get(parts[1], "0")) if len(parts) > 1 and parts[1] else 0
                    return tens * 10 + ones
                # 单个数字
                d = CN_MAP.get(s, "")
                return int(d) if d else None

            # 年月日
            for m in re.finditer(r"([零〇一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日", buf):
                y = _cn_year_to_int(m.group(1))
                mon = _cn_num_to_int(m.group(2))
                day = _cn_num_to_int(m.group(3))
                if y and mon and day:
                    candidates.append(_norm(y, mon, day))
            # 年月（默认1日）
            for m in re.finditer(r"([零〇一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月", buf):
                y = _cn_year_to_int(m.group(1))
                mon = _cn_num_to_int(m.group(2))
                if y and mon:
                    candidates.append(_norm(y, mon, None))
            # 仅年份（默认1月1日）
            for m in re.finditer(r"([零〇一二三四五六七八九]{4})年", buf):
                y = _cn_year_to_int(m.group(1))
                if y:
                    candidates.append(_norm(y, 1, None))
        except Exception:
            pass

        # Compact: YYYYMMDD
        for m in re.finditer(r"\b((?:19|20)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))

        # Compact (YYMMDD): 6位数字（推断世纪，<=29 -> 2000+；否则 1900+）
        for m in re.finditer(r"\b(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b", buf):
            try:
                yy = int(m.group(1))
                year = (2000 + yy) if yy <= 29 else (1900 + yy)
                candidates.append(_norm(year, m.group(2), m.group(3)))
            except Exception:
                pass

        # Dots: YYYY.MM.DD
        for m in re.finditer(r"\b((?:19|20)\d{2})\.(0?[1-9]|1[0-2])\.(0?[1-9]|[12]\d|3[01])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
        # Dots: YYYY.MM
        for m in re.finditer(r"\b((?:19|20)\d{2})\.(0?[1-9]|1[0-2])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), None))

        # US: MM/DD/YYYY 或 M/D/YYYY
        for m in re.finditer(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/((?:19|20)\d{2})\b", buf):
            candidates.append(_norm(m.group(3), m.group(1), m.group(2)))
        # US: MM-DD-YYYY 或 M-D-YYYY
        for m in re.finditer(r"\b(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])-((?:19|20)\d{2})\b", buf):
            candidates.append(_norm(m.group(3), m.group(1), m.group(2)))
        # US: MM/DD/YY（推断世纪）
        for m in re.finditer(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/(\d{2})\b", buf):
            try:
                yy = int(m.group(3))
                year = (2000 + yy) if yy <= 29 else (1900 + yy)
                candidates.append(_norm(year, m.group(1), m.group(2)))
            except Exception:
                pass
        # US: MM-DD-YY（推断世纪）
        for m in re.finditer(r"\b(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])-(\d{2})\b", buf):
            try:
                yy = int(m.group(3))
                year = (2000 + yy) if yy <= 29 else (1900 + yy)
                candidates.append(_norm(year, m.group(1), m.group(2)))
            except Exception:
                pass

        # English: Month DD, YYYY（支持缩写与可选句点）
        for m in re.finditer(r"\b(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b", buf, flags=re.IGNORECASE):
            name = m.group(1).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                candidates.append(_norm(m.group(3), mon, m.group(2)))

        # English（句式+可选星期）：Updated on/As of/Effective ... , Monday, Month DD, YYYY（支持跨行与逗号）
        try:
            sentence_pat = (
                r"(?:\b(on|as\s+of|as\s+at|effective(?:\s+as\s+of)?|updated(?:\s+on)?|last\s+updated|published)\b\s*[:：\-–—]?\s*)?"  # 可选介词/状态词
                r"(?:\b(Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day))\b,?\s*)?"  # 可选星期
                r"\b(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b"
            )
            for m in re.finditer(sentence_pat, buf, flags=re.IGNORECASE | re.DOTALL):
                name = m.group(3).lower().replace(".", "")
                mon = MONTHS.get(name) or MONTHS.get(name[:3])
                if mon:
                    candidates.append(_norm(m.group(5), mon, m.group(4)))
        except Exception:
            pass

        # English: YYYY Month DD（支持缩写）
        for m in re.finditer(r"\b((?:19|20)\d{2})\s+(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+(\d{1,2})\b", buf, flags=re.IGNORECASE):
            name = m.group(2).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                candidates.append(_norm(m.group(1), mon, m.group(3)))

        # English: Month YYYY（默认1号）
        for m in re.finditer(r"\b(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+((?:19|20)\d{2})\b", buf, flags=re.IGNORECASE):
            name = m.group(1).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                candidates.append(_norm(m.group(2), mon, None))

        # English: YYYY Month（默认1号）
        for m in re.finditer(r"\b((?:19|20)\d{2})\s+(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\b", buf, flags=re.IGNORECASE):
            name = m.group(2).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                candidates.append(_norm(m.group(1), mon, None))

        # English: DD Month YYYY（支持序数后缀）
        for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+((?:19|20)\d{2})\b", buf, flags=re.IGNORECASE):
            name = m.group(2).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                candidates.append(_norm(m.group(3), mon, m.group(1)))

        # English: Month DD 'YY / YYYY（支持序数后缀与短年位）
        for m in re.finditer(r"\b(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(?:'|’)?(\d{2,4})\b", buf, flags=re.IGNORECASE):
            name = m.group(1).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                yy = int(m.group(3))
                year = yy if yy > 100 else (2000 + yy if yy <= 29 else 1900 + yy)
                candidates.append(_norm(year, mon, m.group(2)))

        # English: DD Month 'YY（短年位）
        for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+(?:'|’)(\d{2})\b", buf, flags=re.IGNORECASE):
            name = m.group(2).lower().replace(".", "")
            mon = MONTHS.get(name) or MONTHS.get(name[:3])
            if mon:
                yy = int(m.group(3))
                year = 2000 + yy if yy <= 29 else 1900 + yy
                candidates.append(_norm(year, mon, m.group(1)))

        # Month YYYY / YYYY Month 以斜杠或横杠分隔的年月
        for m in re.finditer(r"\b((?:19|20)\d{2})/(0?[1-9]|1[0-2])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), None))
        for m in re.finditer(r"\b((?:19|20)\d{2})-(0?[1-9]|1[0-2])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), None))

        # Chinese flexible: allow spaces and optional separators between 年/月/日
        # Examples: "2023 年 7 月 1 日", "2024年 10月 08日", "2024 年7 月 8 号"
        for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)", buf, flags=re.DOTALL):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
        # Chinese flexible: YYYY 年 MM 月（default day=1）
        for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月", buf, flags=re.DOTALL):
            candidates.append(_norm(m.group(1), m.group(2), None))

        # Quarter: English Q1/Q2/Q3/Q4 with year
        for m in re.finditer(r"\b((?:19|20)\d{2})\s*Q([1-4])\b", buf):
            q = f"Q{m.group(2)}"
            mm = QMAP_EN.get(q)
            if mm:
                candidates.append(_norm(m.group(1), mm, None))
        for m in re.finditer(r"\bQ([1-4])\s*((?:19|20)\d{2})\b", buf):
            q = f"Q{m.group(1)}"
            mm = QMAP_EN.get(q)
            if mm:
                candidates.append(_norm(m.group(2), mm, None))
        # Quarter: Compact forms YYYYQn / QnYYYY
        for m in re.finditer(r"\b((?:19|20)\d{2})Q([1-4])\b", buf):
            q = f"Q{m.group(2)}"
            mm = QMAP_EN.get(q)
            if mm:
                candidates.append(_norm(m.group(1), mm, None))
        for m in re.finditer(r"\bQ([1-4])((?:19|20)\d{2})\b", buf):
            q = f"Q{m.group(1)}"
            mm = QMAP_EN.get(q)
            if mm:
                candidates.append(_norm(m.group(2), mm, None))

        # Quarter: Chinese 年 + 第X季度/ X季度
        for m in re.finditer(r"((?:19|20)\d{2})年(?:第)?([一二三四])季度", buf):
            ch = m.group(2)
            mm = QMAP_ZH.get(ch)
            if mm:
                candidates.append(_norm(m.group(1), mm, None))

        # 下划线分隔：YYYY_MM_DD / YYYY_MM
        for m in re.finditer(r"\b((?:19|20)\d{2})_(0[1-9]|1[0-2])_(0[1-9]|[12]\d|3[01])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
        for m in re.finditer(r"\b((?:19|20)\d{2})_(0[1-9]|1[0-2])\b", buf):
            candidates.append(_norm(m.group(1), m.group(2), None))

        # 欧式数字：DD/MM/YYYY、DD-MM-YYYY，以及短年位
        for m in re.finditer(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/((?:19|20)\d{2})\b", buf):
            candidates.append(_norm(m.group(3), m.group(2), m.group(1)))
        for m in re.finditer(r"\b(0?[1-9]|[12]\d|3[01])-(0?[1-9]|1[0-2])-((?:19|20)\d{2})\b", buf):
            candidates.append(_norm(m.group(3), m.group(2), m.group(1)))
        for m in re.finditer(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/(\d{2})\b", buf):
            try:
                yy = int(m.group(3))
                year = (2000 + yy) if yy <= 29 else (1900 + yy)
                candidates.append(_norm(year, m.group(2), m.group(1)))
            except Exception:
                pass
        for m in re.finditer(r"\b(0?[1-9]|[12]\d|3[01])-(0?[1-9]|1[0-2])-(\d{2})\b", buf):
            try:
                yy = int(m.group(3))
                year = (2000 + yy) if yy <= 29 else (1900 + yy)
                candidates.append(_norm(year, m.group(2), m.group(1)))
            except Exception:
                pass

        # 带标签的日期（优先捕获标签尾随的日期片段，扩大窗口并支持跨行与中文冒号）
        try:
            for lab in LABELS:
                win = EXTRACT_LABEL_WINDOW
                for lm in re.finditer(rf"{lab}\s*[:：\-–—]?\s*(.{{0,{win}}})", buf, flags=re.IGNORECASE | re.DOTALL):
                    tail = lm.group(1)
                    # 简单在 tail 中扫描常见格式
                    for m in re.finditer(r"\b((?:19|20)\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", tail):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    for m in re.finditer(r"\b((?:19|20)\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b", tail):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    for m in re.finditer(r"\b((?:19|20)\d{2})\.(0?[1-9]|1[0-2])\.(0?[1-9]|[12]\d|3[01])\b", tail):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    for m in re.finditer(r"((?:19|20)\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日", tail, flags=re.DOTALL):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    # 中文日期变体：支持空格与分隔符
                    for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)", tail, flags=re.DOTALL):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    for m in re.finditer(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/((?:19|20)\d{2})\b", tail):
                        candidates.append(_norm(m.group(3), m.group(1), m.group(2)))
                    for m in re.finditer(r"\b(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])-((?:19|20)\d{2})\b", tail):
                        candidates.append(_norm(m.group(3), m.group(1), m.group(2)))
                    for m in re.finditer(r"\b(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b", tail, flags=re.IGNORECASE):
                        name = m.group(1).lower().replace(".", "")
                        mon = MONTHS.get(name) or MONTHS.get(name[:3])
                        if mon:
                            candidates.append(_norm(m.group(3), mon, m.group(2)))
                    # 英文 DD Month YYYY（支持序数与跨行）
                    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan(?:\.|uary)?|Feb(?:\.|ruary)?|Mar(?:\.|ch)?|Apr(?:\.|il)?|May|Jun(?:\.|e)?|Jul(?:\.|y)?|Aug(?:\.|ust)?|Sep(?:\.|t|tember)?|Oct(?:\.|ober)?|Nov(?:\.|ember)?|Dec(?:\.|ember)?)\s+((?:19|20)\d{2})\b", tail, flags=re.IGNORECASE | re.DOTALL):
                        name = m.group(2).lower().replace(".", "")
                        mon = MONTHS.get(name) or MONTHS.get(name[:3])
                        if mon:
                            candidates.append(_norm(m.group(3), mon, m.group(1)))
                    # 中文句式：可选星期 + 标准中文日期（跨行）
                    for m in re.finditer(r"(?:星期[一二三四五六日天]|周[一二三四五六日天])?[,，]?\s*((?:19|20)\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日", tail, flags=re.DOTALL):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    # 仅年份推断（在标签邻近窗口内，默认1月1日）
                    for m in re.finditer(r"((?:19|20)\d{2})年", tail):
                        candidates.append(_norm(m.group(1), 1, None))
                    # 季度推断（在标签邻近窗口内）
                    for m in re.finditer(r"((?:19|20)\d{2})年(?:第)?([一二三四])季度", tail):
                        ch = m.group(2)
                        mm = QMAP_ZH.get(ch)
                        if mm:
                            candidates.append(_norm(m.group(1), mm, None))
                # 前缀窗口检查：处理“YYYY年MM月 发布/印发/更新”等前置日期
                for lm in re.finditer(rf"{lab}", buf, flags=re.IGNORECASE):
                    start = lm.start()
                    pre = buf[max(0, start - EXTRACT_LABEL_WINDOW):start]
                    for m in re.finditer(r"\b((?:19|20)\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", pre):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    for m in re.finditer(r"((?:19|20)\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日", pre):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    # 中文日期变体（前缀窗口）：支持空格与分隔符
                    for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)", pre):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    for m in re.finditer(r"\b((?:19|20)\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b", pre):
                        candidates.append(_norm(m.group(1), m.group(2), m.group(3)))
                    # 仅年份推断（默认1月1日）
                    for m in re.finditer(r"((?:19|20)\d{2})年", pre):
                        candidates.append(_norm(m.group(1), 1, None))
        except Exception:
            pass

        # 去重并排序（最新优先）
        unique = sorted(set(candidates), reverse=True)
        return unique

    def _extract_labeled_dates(text: str, labels: List[str]) -> List[str]:
        try:
            buf = _normalize_for_date(text or "")
            results: List[str] = []
            # 中文数字转换工具（与 _extract_date_candidates 保持一致）
            CN_MAP = {"零": "0", "〇": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
            def _cn_year_to_int(ycn: str) -> int | None:
                y = "".join(CN_MAP.get(ch, "") for ch in ycn)
                return int(y) if len(y) == 4 and y.isdigit() else None
            def _cn_num_to_int(s: str | None) -> int | None:
                if not s:
                    return None
                s = s.strip()
                if s == "十":
                    return 10
                if s.startswith("十"):
                    tail = CN_MAP.get(s[1:], "0") if len(s) > 1 else "0"
                    return 10 + int(tail)
                if "十" in s:
                    parts = s.split("十")
                    tens = int(CN_MAP.get(parts[0], "0")) if parts[0] else 1
                    ones = int(CN_MAP.get(parts[1], "0")) if len(parts) > 1 and parts[1] else 0
                    return tens * 10 + ones
                d = CN_MAP.get(s, "")
                return int(d) if d else None

            for lab in labels:
                win = EXTRACT_LABEL_WINDOW
                # 尾随窗口：label 后的邻近区域
                for lm in re.finditer(rf"{lab}\s*[:：\-–—]?\s*(.{{0,{win}}})", buf, flags=re.IGNORECASE | re.DOTALL):
                    tail = lm.group(1)
                    # 常见数字格式
                    for m in re.finditer(r"\b((?:19|20)\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", tail):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    for m in re.finditer(r"\b((?:19|20)\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b", tail):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    for m in re.finditer(r"\b((?:19|20)\d{2})\.(0?[1-9]|1[0-2])\.(0?[1-9]|[12]\d|3[01])\b", tail):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    for m in re.finditer(r"((?:19|20)\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日", tail):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    # 中文日期变体：支持空格与分隔符
                    for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)", tail):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    # 中文数字日期：二〇二四年七月十五日 / 二零二一年七月 等
                    for m in re.finditer(r"([零〇一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日", tail):
                        y = _cn_year_to_int(m.group(1))
                        mon = _cn_num_to_int(m.group(2))
                        day = _cn_num_to_int(m.group(3))
                        if y and mon and day:
                            results.append(f"{y:04d}-{mon:02d}-{day:02d}")
                    for m in re.finditer(r"([零〇一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月", tail):
                        y = _cn_year_to_int(m.group(1))
                        mon = _cn_num_to_int(m.group(2))
                        if y and mon:
                            results.append(f"{y:04d}-{mon:02d}-01")
                    # 仅年份推断（默认1月1日）
                    for m in re.finditer(r"((?:19|20)\d{2})年", tail):
                        results.append(f"{int(m.group(1)):04d}-01-01")
                    for m in re.finditer(r"([零〇一二三四五六七八九]{4})年", tail):
                        y = _cn_year_to_int(m.group(1))
                        if y:
                            results.append(f"{y:04d}-01-01")
                    # 规范文号中的年份：〔2021〕XX号 / (2022)XX
                    for m in re.finditer(r"(?:\(|（|\[|〔|【)\s*((?:19|20)\d{2})\s*(?:\)|）|\]|〕|】)\s*[^\n]{0,30}?号", tail):
                        results.append(f"{int(m.group(1)):04d}-01-01")
                    for m in re.finditer(r"(?:\(|（|\[|〔|【)\s*((?:19|20)\d{2})\s*(?:\)|）|\]|〕|】)", tail):
                        results.append(f"{int(m.group(1)):04d}-01-01")

                # 前缀窗口：label 前的邻近区域
                for lm in re.finditer(rf"{lab}", buf, flags=re.IGNORECASE):
                    start = lm.start()
                    pre = buf[max(0, start - EXTRACT_LABEL_WINDOW):start]
                    for m in re.finditer(r"\b((?:19|20)\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", pre):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    for m in re.finditer(r"((?:19|20)\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日", pre):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    # 中文日期变体（前缀窗口）：支持空格与分隔符
                    for m in re.finditer(r"((?:19|20)\d{2})\s*[-·/]?\s*年\s*[-·/]?\s*(0?[1-9]|1[0-2])\s*[-·/]?\s*月\s*[-·/]?\s*(0?[1-9]|[12]\d|3[01])\s*[-·/]?\s*(?:日|号)", pre):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    for m in re.finditer(r"\b((?:19|20)\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b", pre):
                        results.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                    # 中文数字日期（前缀窗口）
                    for m in re.finditer(r"([零〇一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日", pre):
                        y = _cn_year_to_int(m.group(1))
                        mon = _cn_num_to_int(m.group(2))
                        day = _cn_num_to_int(m.group(3))
                        if y and mon and day:
                            results.append(f"{y:04d}-{mon:02d}-{day:02d}")
                    for m in re.finditer(r"([零〇一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月", pre):
                        y = _cn_year_to_int(m.group(1))
                        mon = _cn_num_to_int(m.group(2))
                        if y and mon:
                            results.append(f"{y:04d}-{mon:02d}-01")
                    for m in re.finditer(r"((?:19|20)\d{2})年", pre):
                        results.append(f"{int(m.group(1)):04d}-01-01")
                    for m in re.finditer(r"([零〇一二三四五六七八九]{4})年", pre):
                        y = _cn_year_to_int(m.group(1))
                        if y:
                            results.append(f"{y:04d}-01-01")
                    # 规范文号中的年份（前缀窗口）
                    for m in re.finditer(r"(?:\(|（|\[|〔|【)\s*((?:19|20)\d{2})\s*(?:\)|）|\]|〕|】)\s*[^\n]{0,30}?号", pre):
                        results.append(f"{int(m.group(1)):04d}-01-01")
                    for m in re.finditer(r"(?:\(|（|\[|〔|【)\s*((?:19|20)\d{2})\s*(?:\)|）|\]|〕|】)", pre):
                        results.append(f"{int(m.group(1)):04d}-01-01")
            # 返回去重后的日期集合（升序，用于 earliest/最新选择）
            return sorted(set(results))
        except Exception:
            return []

    # 全局标签集合（用于 label 专用提取与相对短语推断）
    EFFECTIVE_LABELS: List[str] = [
        # 英文
        "effective", "effective date", "effective as of", "comes into force", "enter into force",
        # 中文
        "生效", "生效日期", "施行", "施行日期", "实施", "实施日期", "执行", "执行日期", "适用日期", "适用时间",
    ]

    EXPIRY_LABELS_GLOBAL: List[str] = [
        # 英文常见表达
        "expiry", "expiry date", "expires", "expires on", "valid until", "valid thru", "until",
        "expiration", "expiration date", "end date", "valid through", "effective until",
        # 中文常见表达（扩充废止/停止施行等）
        "有效期", "有效期至", "有效至", "适用期", "适用期至", "截止", "截至", "至",
        "到期", "到期日", "到期日期", "终止日期", "失效日期", "结束日期", "有效截止",
        "废止", "废止日期", "停止施行", "停止执行", "暂停执行", "终止",
    ]

    FILING_LABELS_GLOBAL: List[str] = [
        # 英文
        "filing date", "filed on", "registration date", "record filing date", "approval date", "approved on",
        # 中文
        "备案日期", "备案时间", "备案版本", "报备日期", "报备时间", "报批日期", "批复日期", "印发日期", "发布印发",
    ]

    def _extract_effective_date(text: str) -> str | None:
        cands = _extract_labeled_dates(text or "", EFFECTIVE_LABELS)
        # 生效通常取最早（earliest）
        return _select_earliest(cands) if cands else None

    def _extract_expiry_date(text: str) -> str | None:
        cands = _extract_labeled_dates(text or "", EXPIRY_LABELS_GLOBAL)
        return cands[-1] if cands else None

    def _extract_filing_date(text: str) -> str | None:
        cands = _extract_labeled_dates(text or "", FILING_LABELS_GLOBAL)
        return cands[0] if cands else None

    def _infer_relative_dates(text: str, publish: str | None, last_updated: str | None) -> Tuple[str | None, str | None]:
        """
        依据相对短语推断生效/废止日期：
        - 生效：自发布/公布/印发之日起施行/实施/执行/生效；自即日起施行/实施/执行/生效
        - 废止：自发布/公布/印发之日起废止/失效/停止施行/停止执行；自即日起废止/失效/停止施行
        - 显式区间：自YYYY年MM月DD日起至YYYY年MM月DD日止 -> 生效=起，废止=止
        当短语未给出具体日期时，优先以 publish，其次以 last_updated 作为推断源。
        """
        try:
            buf = _normalize_for_date(text or "")

            def _norm(y: int, m: int, d: int) -> str:
                return f"{y:04d}-{m:02d}-{d:02d}"

            eff_rel: str | None = None
            exp_rel: str | None = None

            # 显式区间：自YYYY年MM月DD日起至YYYY年MM月DD日(止/截止)
            m = re.search(r"自\s*((?:19|20)\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月\s*(0?[1-9]|[12]\d|3[01])\s*日\s*(?:起|开始)\s*(?:至|到|截至)\s*((?:19|20)\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月\s*(0?[1-9]|[12]\d|3[01])\s*日", buf)
            if m:
                try:
                    eff_rel = _norm(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    exp_rel = _norm(int(m.group(4)), int(m.group(5)), int(m.group(6)))
                except Exception:
                    pass

            # 显式起始：自YYYY年MM月DD日起施行/实施/执行/生效
            if eff_rel is None:
                m2 = re.search(r"自\s*((?:19|20)\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月\s*(0?[1-9]|[12]\d|3[01])\s*日\s*(?:起|开始).{0,12}?(?:施行|实施|执行|生效)", buf)
                if m2:
                    try:
                        eff_rel = _norm(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
                    except Exception:
                        pass

            # 显式废止：自YYYY年MM月DD日起废止/失效/停止施行/停止执行
            if exp_rel is None:
                m3 = re.search(r"自\s*((?:19|20)\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月\s*(0?[1-9]|[12]\d|3[01])\s*日\s*(?:起|开始).{0,12}?(?:废止|失效|停止施行|停止执行|暂停执行|终止)", buf)
                if m3:
                    try:
                        exp_rel = _norm(int(m3.group(1)), int(m3.group(2)), int(m3.group(3)))
                    except Exception:
                        pass

            # 相对短语：自发布/公布/印发之日起 施行/实施/执行/生效
            if eff_rel is None:
                if re.search(r"自(?:发布|公布|印发)[之]?日(?:起|开始).{0,12}?(?:施行|实施|执行|生效)", buf) or re.search(r"自(?:即日|即日起).{0,12}?(?:施行|实施|执行|生效)", buf):
                    eff_rel = publish or last_updated

            # 相对短语：自发布/公布/印发之日起 废止/失效/停止施行/停止执行
            if exp_rel is None:
                if re.search(r"自(?:发布|公布|印发)[之]?日(?:起|开始).{0,12}?(?:废止|失效|停止施行|停止执行|暂停执行|终止)", buf) or re.search(r"自(?:即日|即日起).{0,12}?(?:废止|失效|停止施行|停止执行|暂停执行|终止)", buf):
                    exp_rel = last_updated or publish

            # 英文：effective immediately / effective upon publication
            if eff_rel is None and re.search(r"\beffective\s+immediately\b", buf, flags=re.IGNORECASE):
                eff_rel = publish or last_updated
            if eff_rel is None and re.search(r"\beffective\s+upon\s+(publication|issuance)\b", buf, flags=re.IGNORECASE):
                eff_rel = publish or last_updated
            # 英文：repealed/terminated effective immediately
            if exp_rel is None and re.search(r"\b(repealed|terminated|expires)\s+immediately\b", buf, flags=re.IGNORECASE):
                exp_rel = last_updated or publish

            return eff_rel, exp_rel
        except Exception:
            return None, None

    def _select_earliest(cands: List[str]) -> str | None:
        if not cands:
            return None
        return sorted(set(cands))[0]

    def _select_latest(cands: List[str]) -> str | None:
        if not cands:
            return None
        return sorted(set(cands))[-1]

    def _pdf_creation_date_to_iso(s: str) -> str | None:
        """将 PDF 元数据中的 CreationDate/ModDate 转为 YYYY-MM-DD。
        常见格式：D:YYYYMMDDHHmmSSO、YYYYMMDDHHmmSSZ，或直接 YYYY-MM-DD。
        仅提取前 8 位日期部分。
        """
        try:
            if not s:
                return None
            s = str(s).strip()
            # 优先匹配带 D: 前缀的紧凑格式
            m = re.search(r"D:(\d{4})(\d{2})(\d{2})", s)
            if not m:
                # 回退：任意出现连续8位的 YYYYMMDD
                m = re.search(r"(\d{4})(\d{2})(\d{2})", s)
            if m:
                y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return f"{y:04d}-{mm:02d}-{dd:02d}"
            # 回退：标准分隔格式
            m2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
            if m2:
                y, mm, dd = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                return f"{y:04d}-{mm:02d}-{dd:02d}"
        except Exception:
            return None
        return None

    def _extract_pdf_creation_date(pdf_path: str) -> str | None:
        """从 PDF 文件元数据提取 CreationDate/ModDate，返回 YYYY-MM-DD。"""
        try:
            reader = None
            try:
                # 优先使用 PyPDF2
                from PyPDF2 import PdfReader as _PdfReader  # type: ignore
                reader = _PdfReader(pdf_path)
            except Exception:
                try:
                    # 回退到 pypdf
                    from pypdf import PdfReader as _PdfReader  # type: ignore
                    reader = _PdfReader(pdf_path)
                except Exception:
                    reader = None
            if reader is None:
                return None

            # 新版接口：metadata 字典
            vals: List[str] = []
            meta = getattr(reader, "metadata", None)
            if meta:
                try:
                    val = meta.get("/CreationDate") or meta.get("CreationDate") or meta.get("/ModDate") or meta.get("ModDate")
                    if val:
                        vals.append(str(val))
                except Exception:
                    pass

            # 旧版接口：getDocumentInfo()
            if not vals:
                try:
                    info = reader.getDocumentInfo()  # type: ignore[attr-defined]
                    if info:
                        val = info.get("/CreationDate") or info.get("/ModDate")
                        if val:
                            vals.append(str(val))
                except Exception:
                    pass

            for raw in vals:
                iso = _pdf_creation_date_to_iso(raw)
                if iso:
                    return iso
            return None
        except Exception:
            return None

    def _extract_dates_from_layout(pdf_path: str, scan_last_pages: int = 2, scan_first_pages: int = 1) -> List[str]:
        """利用版面结构抽取候选日期：优先首尾页与可能的附则/签章区域。
        需要 PyMuPDF；若不可用或失败则返回空列表。
        """
        cands: List[str] = []
        try:
            if fitz is None or not pdf_path or not os.path.exists(pdf_path):
                return []
            doc = fitz.open(pdf_path)
            total = doc.page_count or 0
            texts: List[str] = []
            # 首页
            for i in range(min(scan_first_pages, max(total, 0))):
                try:
                    texts.append(doc.load_page(i).get_text("text") or "")
                except Exception:
                    continue
            # 尾页
            for i in range(max(total - scan_last_pages, 0), total):
                try:
                    texts.append(doc.load_page(i).get_text("text") or "")
                except Exception:
                    continue
            doc.close()
            joined = _normalize_for_date("\n".join(texts))
            # 优先标签邻近抽取
            lc = _extract_labeled_dates(joined)  # type: ignore[name-defined]
            for k in ["effective_date", "publish_date", "last_updated_date", "expiry_date", "filing_date"]:
                vv = lc.get(k)
                if vv:
                    cands.append(str(vv))
            # 回退一般候选
            more = _extract_date_candidates(joined, {})  # type: ignore[name-defined]
            cands.extend(more)
            return sorted(set([x[:10] for x in cands if x]))
        except Exception:
            return []

    def _enforce_date_consistency(eff: str | None, pub: str | None, last: str | None, expiry: str | None) -> Tuple[str | None, str | None, str | None, str | None]:
        """确保日期逻辑一致：publish <= effective <= last <= expiry（若存在）。不满足时保守回退空或早/晚边界。"""
        def _to_int(x: str | None) -> int | None:
            try:
                if not x:
                    return None
                y, m, d = x.split("-")
                return int(y) * 10000 + int(m) * 100 + int(d)
            except Exception:
                return None
        pi, ei, li, xi = _to_int(pub), _to_int(eff), _to_int(last), _to_int(expiry)
        # publish 与 effective
        if pi is not None and ei is not None and pi > ei:
            pub = None
        # effective 与 last
        if ei is not None and li is not None and ei > li:
            last = None
        # last 与 expiry
        if li is not None and xi is not None and li > xi:
            expiry = None
        return eff, pub, last, expiry

    def _score_date_candidates(cands: List[str], text: str) -> List[str]:
        """对候选日期进行简易打分排序：标签邻近、语义位置、出现频次等。
        返回按分数降序的去重候选列表。
        """
        if not cands:
            return []
        uniq = sorted(set([x[:10] for x in cands if x]))
        anchors = [
            "施行", "生效", "有效期起", "有效期至", "截止", "印发", "发布", "公布", "修订", "备案",
            "有效期", "执行", "签发", "批准", "批复", "实施", "起始", "终止",
        ]
        scores: Dict[str, float] = {u: 0.0 for u in uniq}
        for u in uniq:
            freq = text.count(u)
            scores[u] += min(freq, 3) * 1.0
            try:
                for a in anchors:
                    idx = text.find(a)
                    if idx != -1:
                        dpos = text.find(u)
                        if dpos != -1 and abs(dpos - idx) <= EXTRACT_LABEL_WINDOW:
                            scores[u] += 2.0
            except Exception:
                pass
            try:
                pos = text.find(u)
                if pos != -1:
                    rel = pos / max(len(text), 1)
                    if rel < 0.1 or rel > 0.9:
                        scores[u] += 0.5
            except Exception:
                pass
        def _to_int(x: str) -> int:
            try:
                y, m, d = x.split("-")
                return int(y) * 10000 + int(m) * 100 + int(d)
            except Exception:
                return 0
        return sorted(uniq, key=lambda x: (-scores.get(x, 0.0), _to_int(x)))

    def _hybrid_date_candidates(text: str, meta: Dict[str, Any] | None = None, pdf_path: str = "") -> List[str]:
        """规则与学习混合器：综合标签抽取、通用启发式、版面结构、PDF元数据，产出融合候选。"""
        meta = meta or {}
        pool: List[str] = []
        try:
            lab = _extract_labeled_dates(text)
            for k in ["effective_date", "publish_date", "last_updated_date", "expiry_date", "filing_date"]:
                vv = lab.get(k)
                if vv:
                    pool.append(str(vv))
        except Exception:
            pass
        try:
            ht = _extract_date_candidates(text, meta)
            pool.extend(ht)
        except Exception:
            pass
        try:
            if pdf_path and pdf_path.lower().endswith(".pdf") and os.path.exists(pdf_path):
                ly = _extract_dates_from_layout(pdf_path)
                pool.extend(ly)
                iso = _extract_pdf_creation_date(pdf_path)
                if iso:
                    pool.append(iso)
        except Exception:
            pass
        return _score_date_candidates(pool, text)

    def _collect_version_chain_dates(doc_obj: Any) -> List[str]:
        """版本链对齐：基于同系列文档（同标题/同基名）聚类，收集相邻版本的日期作为候选。"""
        cands: List[str] = []
        try:
            title = str(getattr(doc_obj, "title", "") or "")
            fp = str(getattr(doc_obj, "file_path", "") or "")
            base = os.path.splitext(os.path.basename(fp))[0] if fp else ""
            keys = [x for x in [title, base] if x]
            if not keys:
                return []
            session = db_manager.get_session()
            with session as s:
                for k in keys:
                    try:
                        q = s.query(Document).filter(Document.title == k)
                        for other in q.limit(50).all():
                            md = getattr(other, "metadata", {}) or {}
                            for fld in ["publish_date", "effective_date", "last_updated_date", "expiry_date"]:
                                vv = str(md.get(fld, "") or "").strip()[:10]
                                if vv:
                                    cands.append(vv)
                    except Exception:
                        continue
        except Exception:
            pass
        return sorted(set([x[:10] for x in cands if x]))

    # 连接数据库以获取文件名/路径进行日期解析
    session = None
    try:
        session = db_manager.create_session()
    except Exception:
        session = None

    processed_docs = 0
    identified_missing_count = 0
    t0 = time.perf_counter()

    # 记录基线全局参数，确保每个文档组处理后回滚，避免跨组污染
    baseline_label_window = EXTRACT_LABEL_WINDOW
    baseline_enable_hybrid = enable_hybrid
    baseline_enable_version_chain = enable_version_chain

    for doc_key in doc_keys:
        items = groups.get(doc_key, [])

        # 分策略：根据该文档的元数据情况动态调整扫描窗口与启用能力
        group_scan_pages = getattr(args, "scan_pages", 3)
        strategy_name = "baseline"
        if getattr(args, "auto_strategy", False):
            try:
                has_publish = any(str((md or {}).get("publish_date") or "").strip() and str((md or {}).get("publish_date") or "").strip() != "未知" for _, md, _ in items)
                miss_eff_or_last = any((not str((md or {}).get("effective_date") or "").strip()) or (not str((md or {}).get("last_updated_date") or "").strip()) for _, md, _ in items)
                has_any_required = any(str((md or {}).get(k) or "").strip() for _, md, _ in items for k in REQUIRED_DATE_FIELDS)
                # 使用已在函数开头声明的模块级标签窗口参数
                if has_publish and miss_eff_or_last:
                    strategy_name = "publish_missing_others"
                    EXTRACT_LABEL_WINDOW = max(getattr(args, "neighbor_window", 300), 1000)
                    group_scan_pages = max(getattr(args, "scan_pages", 3), 14)
                    enable_hybrid = True
                    enable_version_chain = True
                elif not has_any_required:
                    strategy_name = "no_signal"
                    EXTRACT_LABEL_WINDOW = max(getattr(args, "neighbor_window", 300), 1200)
                    group_scan_pages = max(getattr(args, "scan_pages", 3), 16)
                    enable_hybrid = True
                strategy_stats[strategy_name] = strategy_stats.get(strategy_name, 0) + 1
                logger.debug(f"文档 {doc_key} 应用策略：{strategy_name}，label_window={EXTRACT_LABEL_WINDOW}，scan_pages={group_scan_pages}")
            except Exception:
                pass

        # 统计该文档原始缺失的块数量
        try:
            identified_missing_count += sum(1 for _, md, _ in items if is_missing_date_metadata(md))
        except Exception:
            pass

        # 收集已存在的日期
        existing_dates: List[str] = []
        for _, md, _ in items:
            for k in REQUIRED_DATE_FIELDS:
                v = md.get(k)
                if v and str(v).strip() and str(v).strip() != "未知":
                    existing_dates.append(str(v).strip()[:10])

        eff: str | None = None
        last: str | None = None
        pub: str | None = None
        expiry: str | None = None
        filing: str | None = None
        date_source: str | None = None

        # 首选：若文档任意块已有日期，则统一回填到所有缺失块
        if existing_dates:
            eff = _select_earliest(existing_dates)
            last = _select_latest(existing_dates)
            pub = eff
            date_source = "existing"
            # 即便已有必选日期，也尝试解析可选日期字段（expiry/filing）
            try:
                # 聚合前 N 页文本作为近邻扫描上下文
                sample_text_opt = ""
                try:
                    page_contents = []
                    for _, md, c in items:
                        pn = md.get("page_number")
                        try:
                            pn_int = int(pn) if pn is not None else 0
                        except Exception:
                            pn_int = 0
                        page_contents.append((pn_int, c or ""))
                    valid_pages = [(pn, c) for pn, c in page_contents if pn > 0]
                    valid_pages.sort(key=lambda x: x[0])
                    agg = [c for _, c in valid_pages[: max(group_scan_pages, 1)]]
                    if agg:
                        sample_text_opt = _normalize_for_date(("\n".join(agg))[: args.max_content_chars])
                    else:
                        first_page = [c for _, md, c in items if (md.get("page_number") or 0) == 1]
                        sample_text_opt = _normalize_for_date((first_page[0] if first_page else (items[0][2] if items else ""))[: args.max_content_chars])
                except Exception:
                    sample_text_opt = _normalize_for_date(((items[0][2] if items else "")[: args.max_content_chars]))

                # 若配置了档案官API，则优先尝试从API获取可选字段
                if not fallback_mode and api_url and api_key:
                    try:
                        arch = call_archiver_api(api_url, api_key, str(doc_key), (sample_text_opt or "")[:args.max_content_chars], items[0][1] if items else {}, api_model)
                        ex = (str(arch.get("expiry_date") or "").strip()[:10] if arch else "")
                        fi = (str(arch.get("filing_date") or "").strip()[:10] if arch else "")
                        if ex:
                            expiry = ex
                        if fi:
                            filing = fi
                    except Exception:
                        pass

                # 启发式回退解析可选日期
                if expiry is None:
                    try:
                        expiry = _extract_expiry_date((sample_text_opt or "")[:args.max_content_chars])
                    except Exception:
                        expiry = None
                if filing is None:
                    try:
                        filing = _extract_filing_date((sample_text_opt or "")[:args.max_content_chars])
                    except Exception:
                        filing = None
                # 相对短语推断：若仍缺失，利用 publish/last 推断生效/废止
                try:
                    eff_rel, exp_rel = _infer_relative_dates((sample_text_opt or "")[:args.max_content_chars], pub, last)
                    if eff is None and eff_rel:
                        eff = eff_rel
                    if expiry is None and exp_rel:
                        expiry = exp_rel
                except Exception:
                    pass
            except Exception:
                pass
        else:
            # 次选：从首页内容（或第一个块）抽取
            sample_text = ""
            # 聚合前 N 页文本（优先有页码的内容），限制最大长度
            try:
                page_contents = []
                for _, md, c in items:
                    pn = md.get("page_number")
                    try:
                        pn_int = int(pn) if pn is not None else 0
                    except Exception:
                        pn_int = 0
                    page_contents.append((pn_int, c or ""))
                # 过滤有效页码并排序，取前 N 页
                valid_pages = [(pn, c) for pn, c in page_contents if pn > 0]
                valid_pages.sort(key=lambda x: x[0])
                agg = [c for _, c in valid_pages[: max(group_scan_pages, 1)]]
                if agg:
                    sample_text = _normalize_for_date(("\n".join(agg))[: args.max_content_chars])
                else:
                    # 回退到第一页或第一个块
                    first_page = [c for _, md, c in items if (md.get("page_number") or 0) == 1]
                    sample_text = _normalize_for_date((first_page[0] if first_page else (items[0][2] if items else ""))[: args.max_content_chars])
            except Exception:
                # 兜底回退：第一个块
                sample_text = _normalize_for_date(((items[0][2] if items else "")[: args.max_content_chars]))

            # 优先调用档案官API抽取（非回退模式）
            cands: List[str] = []
            if not fallback_mode and api_url and api_key:
                try:
                    arch = call_archiver_api(api_url, api_key, str(doc_key), (sample_text or "")[:args.max_content_chars], items[0][1] if items else {}, api_model)
                    arch_cands: List[str] = []
                    for k in REQUIRED_DATE_FIELDS:
                        vv = str(arch.get(k, "")).strip()[:10]
                        if vv:
                            arch_cands.append(vv)
                    # 扩展字段（若存在）
                    try:
                        _exp = str(arch.get("expiry_date", "")).strip()[:10] or str(arch.get("valid_until", "")).strip()[:10]
                        expiry = _exp or expiry
                    except Exception:
                        pass
                    try:
                        _fil = str(arch.get("filing_date", "")).strip()[:10]
                        filing = _fil or filing
                    except Exception:
                        pass
                    if arch_cands:
                        cands = arch_cands
                        date_source = "archiver_api"
                except Exception:
                    # 若档案官失败，则退化到启发式
                    pass

            # 启发式抽取（若档案官未给出候选）
            if not cands:
                ht_cands = _extract_date_candidates((sample_text or "")[:args.max_content_chars], items[0][1] if items else {})
                if ht_cands:
                    cands = ht_cands
                    date_source = "heuristic_text"
            # 非近邻兜底：在该文档所有采样块中进行全局扫描（归一化后）
            if not cands:
                try:
                    all_joined = _normalize_for_date(("\n".join([c or "" for _, _, c in items]))[: args.max_content_chars])
                    gl_cands = _extract_date_candidates(all_joined, items[0][1] if items else {})
                    if gl_cands:
                        cands = gl_cands
                        date_source = "heuristic_global"
                except Exception:
                    pass
            # 标签专用：生效日期增强（加入候选集）
            try:
                el = _extract_effective_date((sample_text or "")[:args.max_content_chars])
                if el:
                    cands = sorted(set(cands + [el]))
            except Exception:
                pass
            # 启发式提取有效期与备案日期
            if expiry is None:
                try:
                    expiry = _extract_expiry_date((sample_text or "")[:args.max_content_chars])
                except Exception:
                    expiry = None
            if filing is None:
                try:
                    filing = _extract_filing_date((sample_text or "")[:args.max_content_chars])
                except Exception:
                    filing = None

            # 规则与学习混合器：综合多源候选并打分（若前述仍无候选且开启混合器）
            if not cands and enable_hybrid:
                try:
                    pdf_path = ""
                    fusion = _hybrid_date_candidates((sample_text or "")[:args.max_content_chars], items[0][1] if items else {}, pdf_path)
                    if fusion:
                        cands = fusion
                        date_source = "hybrid_mixer"
                except Exception:
                    pass

            # 再次：从文件名/路径解析（通过数据库）
            if not cands and session is not None:
                try:
                    doc_obj = None
                    # 解析 doc_key 并查询数据库
                    if isinstance(doc_key, str):
                        if doc_key.startswith("id:"):
                            _id = doc_key[3:]
                            if _id.isdigit():
                                doc_obj = session.query(Document).filter(Document.id == int(_id)).first()
                        elif doc_key.startswith("path:"):
                            _path = doc_key[5:]
                            doc_obj = session.query(Document).filter(Document.file_path == _path).first()
                        elif doc_key.startswith("name:"):
                            _name = doc_key[5:]
                            doc_obj = session.query(Document).filter(Document.original_filename == _name).first()
                            if doc_obj is None:
                                doc_obj = session.query(Document).filter(Document.filename == _name).first()
                    else:
                        try:
                            doc_obj = session.query(Document).filter(Document.id == int(doc_key)).first()
                        except Exception:
                            doc_obj = None

                    fn = ""
                    if doc_obj:
                        fn = " ".join([str(doc_obj.filename or ""), str(doc_obj.original_filename or ""), str(doc_obj.file_path or "")])
                    if fn:
                        fn_cands = _extract_date_candidates(fn, {})
                        if fn_cands:
                            cands = fn_cands
                            date_source = "filename_path"
                    # 版面结构抽取：首尾页扫描获取候选
                    if (not cands) and doc_obj:
                        try:
                            pdf_path = str(getattr(doc_obj, "file_path", "") or "")
                            if pdf_path.lower().endswith(".pdf") and os.path.exists(pdf_path):
                                lay_cands = _extract_dates_from_layout(pdf_path)
                                if lay_cands:
                                    cands = lay_cands
                                    date_source = "layout_scan"
                        except Exception:
                            pass
                    # 若文件名/路径未能提取候选，则尝试 PDF 元数据兜底（仅当为 .pdf 且路径存在）
                    if (not cands) and doc_obj:
                        try:
                            pdf_path = str(getattr(doc_obj, "file_path", "") or "")
                            if pdf_path.lower().endswith(".pdf") and os.path.exists(pdf_path):
                                iso = _extract_pdf_creation_date(pdf_path)
                                if iso:
                                    cands = [iso]
                                    date_source = "pdf_creation_date"
                        except Exception:
                            pass
                    # 若仍无候选，则尝试文件时间戳兜底：优先使用数据库 upload_time，其次文件系统 mtime
                    if (not cands) and doc_obj:
                        try:
                            iso: str | None = None
                            up = getattr(doc_obj, "upload_time", None)
                            if up:
                                try:
                                    # 直接 datetime
                                    if isinstance(up, datetime):
                                        iso = up.strftime("%Y-%m-%d")
                                    else:
                                        s = str(up)
                                        # 常见格式尝试
                                        fmts = [
                                            "%Y-%m-%d %H:%M:%S",
                                            "%Y-%m-%d",
                                            "%Y/%m/%d %H:%M:%S",
                                            "%Y/%m/%d",
                                            "%Y.%m.%d %H:%M:%S",
                                            "%Y.%m.%d",
                                        ]
                                        for fmt in fmts:
                                            try:
                                                dt = datetime.strptime(s, fmt)
                                                iso = dt.strftime("%Y-%m-%d")
                                                break
                                            except Exception:
                                                continue
                                        if iso is None:
                                            try:
                                                dt = datetime.fromisoformat(s)
                                                iso = dt.strftime("%Y-%m-%d")
                                            except Exception:
                                                pass
                                except Exception:
                                    iso = None
                            # 回退到文件系统 mtime
                            if iso is None:
                                fp = str(getattr(doc_obj, "file_path", "") or "")
                                if fp and os.path.exists(fp):
                                    try:
                                        ts = os.path.getmtime(fp)
                                        iso = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                                    except Exception:
                                        iso = None
                            if iso:
                                cands = [iso]
                                date_source = "file_timestamp"
                        except Exception:
                            pass
                    # 目录年份占位兜底：从父目录/路径中提取四位年份，默认填充为当年1月1日
                    if (not cands) and doc_obj:
                        try:
                            fp = str(getattr(doc_obj, "file_path", "") or "")
                            candidate_year: int | None = None
                            if fp:
                                # 分析路径片段，优先父目录名中的 20xx/19xx
                                parts = re.split(r"[\\/]+", fp)
                                # 倒序优先父目录
                                for seg in reversed(parts[:-1]):
                                    m = re.search(r"((?:19|20)\d{2})", seg)
                                    if m:
                                        try:
                                            candidate_year = int(m.group(1))
                                            break
                                        except Exception:
                                            continue
                            if candidate_year:
                                iso = f"{candidate_year}-01-01"
                                cands = [iso]
                                date_source = "dir_year_placeholder"
                        except Exception:
                            pass
                    # 版本链对齐：同系列文档日期回填（若仍无候选且开启版本链）
                    if (not cands) and doc_obj and enable_version_chain:
                        try:
                            vc = _collect_version_chain_dates(doc_obj)
                            if vc:
                                cands = vc
                                date_source = "version_chain"
                        except Exception:
                            pass
                except Exception:
                    pass

            eff = _select_earliest(cands)
            last = _select_latest(cands)
            pub = eff
            # 相对短语推断（若仍缺失）：基于 publish/last 推断生效/废止
            try:
                eff_rel, exp_rel = _infer_relative_dates((sample_text or "")[:args.max_content_chars], pub, last)
                if eff is None and eff_rel:
                    eff = eff_rel
                if expiry is None and exp_rel:
                    expiry = exp_rel
            except Exception:
                pass
            # 候选打分排序（用于选择时的保守偏好）；仅在存在多个候选时应用
            try:
                if cands and len(set(cands)) > 1:
                    cands = _score_date_candidates(cands, (sample_text or "")[:args.max_content_chars])
            except Exception:
                pass
            # 一致性约束：publish <= effective <= last <= expiry（若存在）
            try:
                eff, pub, last, expiry = _enforce_date_consistency(eff, pub, last, expiry)
            except Exception:
                pass

        # 构造更新并写入：仅对缺失块执行更新
        doc_update_count = 0
        for chunk_id, md, _ in items:
            new_md = dict(md)
            if eff:
                new_md["effective_date"] = eff
                field_update_counts["effective_date"] += 1
            if last:
                new_md["last_updated_date"] = last
                field_update_counts["last_updated_date"] += 1
            if pub:
                new_md["publish_date"] = pub
                field_update_counts["publish_date"] += 1
            if expiry:
                new_md["expiry_date"] = expiry
                if not new_md.get("valid_until"):
                    new_md["valid_until"] = expiry
                field_update_counts["expiry_date"] += 1
            if filing:
                new_md["filing_date"] = filing
                field_update_counts["filing_date"] += 1
            # 若更新后在必选或可选日期字段中至少存在一个值，则写入
            try:
                has_any = False
                for k in REQUIRED_DATE_FIELDS + OPTIONAL_DATE_FIELDS:
                    vv = str(new_md.get(k, "") or "").strip()
                    if vv and vv != "未知":
                        has_any = True
                        break
            except Exception:
                has_any = not is_missing_date_metadata(new_md)
            if has_any:
                updates.append((chunk_id, new_md))
                doc_update_count += 1
            else:
                failures.append(chunk_id)

        # 记录来源统计与弱信号（PDF/文件时间戳/目录年份兜底）标记（按块计数）
        try:
            if doc_update_count > 0 and date_source:
                source_stats[date_source] = source_stats.get(date_source, 0) + doc_update_count
                if date_source in ("pdf_creation_date", "file_timestamp", "dir_year_placeholder"):
                    weak_signal_doc_keys.append(str(doc_key))
        except Exception:
            pass

        # 回滚到基线参数，避免策略覆盖影响后续文档组
        try:
            EXTRACT_LABEL_WINDOW = baseline_label_window
            enable_hybrid = baseline_enable_hybrid
            enable_version_chain = baseline_enable_version_chain
        except Exception:
            pass

        processed_docs += 1
        if processed_docs % 50 == 0 or processed_docs == len(doc_keys):
            elapsed = max(0.001, time.perf_counter() - t0)
            rate = round(processed_docs / elapsed, 2)
            logger.info(f"文件级进度：{processed_docs}/{len(doc_keys)}（{rate} docs/s），待写入 {len(updates)}，失败 {len(failures)}")

    # 关闭会话
    try:
        if session is not None:
            db_manager.close_session(session)
    except Exception:
        pass

    # 执行批量更新
    success_count, batch_failed_ids = batch_update_dates(updates, salvage_on_batch_failure=args.salvage_on_batch_failure)
    failures.extend(batch_failed_ids)

    duration = round(time.perf_counter() - start_ts, 3)
    logger.info(f"批量更新完成：成功 {success_count}，失败 {len(failures)}，耗时 {duration}s")

    # 执行后验证
    integrity = verify_database_integrity()
    # 字段覆盖统计（按文件聚合）
    try:
        ids2, docs2, metas2 = fetch_all_documents(batch_size=1000)
        def _group_key_for_stats(md: Dict[str, Any], chunk_id: str) -> str:
            fp = str(md.get("file_path") or "").strip()
            if fp:
                return f"path:{fp}"
            sf = str(md.get("source_file") or "").strip()
            if sf:
                return f"name:{sf}"
            return f"chunk:{chunk_id}"
        per_doc_fields: Dict[str, Dict[str, bool]] = {}
        for did, md in zip(ids2, metas2):
            key = _group_key_for_stats(md or {}, did)
            f = per_doc_fields.setdefault(key, {"publish_date": False, "last_updated_date": False, "effective_date": False, "expiry_date": False, "filing_date": False})
            for kk in list(f.keys()):
                vv = str((md or {}).get(kk) or "").strip()
                if vv and vv != "未知":
                    f[kk] = True
        field_presence_counts = {k: 0 for k in ["publish_date", "last_updated_date", "effective_date", "expiry_date", "filing_date"]}
        complete_4_required = 0
        for _, flags in per_doc_fields.items():
            for kk, val in flags.items():
                if val:
                    field_presence_counts[kk] += 1
            if flags.get("publish_date") and flags.get("last_updated_date") and flags.get("expiry_date") and flags.get("filing_date"):
                complete_4_required += 1
    except Exception:
        field_presence_counts = {k: 0 for k in ["publish_date", "last_updated_date", "effective_date", "expiry_date", "filing_date"]}
        complete_4_required = 0
    report = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scanned": len(ids),
        "identified_missing": int(identified_missing_count),
        "updated_success": success_count,
        "update_failed": len(failures),
        "failed_ids": failures,
        "verify": integrity,
        "duration_seconds": duration,
        "source_stats": source_stats,
        "weak_signal_doc_keys": weak_signal_doc_keys,
        "field_update_counts": field_update_counts,
        "field_presence_counts": field_presence_counts,
        "complete_4_required_docs": complete_4_required,
        "strategy_stats": strategy_stats,
        "notes": "weak_signal_doc_keys 为通过 PDF 元数据 CreationDate/ModDate、文件时间戳(file_timestamp) 或目录年份占位(dir_year_placeholder) 兜底获取的日期来源",
    }

    # 输出报告文件
    base = os.path.join(args.report_dir, f"backfill_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='utf-8'><title>Backfill Report</title></head><body>")
        f.write("<h2>元数据补全报告</h2>")
        f.write("<pre>" + json.dumps(report, ensure_ascii=False, indent=2) + "</pre>")
        f.write("</body></html>")

    logger.info(f"报告已生成：{base}.json / {base}.html")


if __name__ == "__main__":
    main()
