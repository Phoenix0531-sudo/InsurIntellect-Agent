#!/usr/bin/env python3
"""
InsurIntellect Agent - Data Ingestion Pipeline
=============================================

This script handles the data initialization phase of the project:
- Reads all PDF documents from the configured directory
- Uses AI to extract metadata from document snippets
- Chunks documents using LangChain text splitters
- Builds a local ChromaDB vector database with embeddings

Author: InsurIntellect Agent Development Team
Version: 1.0.0
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import shutil
import hashlib
import asyncio
import pickle

# BM25 and Chinese tokenizer
from rank_bm25 import BM25Plus
import jieba

# LangChain imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
try:
    from langchain_core.documents import Document
except Exception:
    from langchain.schema import Document

# Project imports
from app.core.config import settings
from app.prompts import DIGITAL_ARCHIVIST_PROMPT
from app.core.chromadb_manager import chroma_manager
from app.core.app_logging import get_logger as _get_logger
from app.services.document_parser_service import DocumentParserService
from app.services.llm_service import LLMService
from app.core.database import init_db, db_manager
from app.models.database_models import DocumentMetadata

# OCR imports
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from dotenv import load_dotenv

# 可选YAML 配置支持
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 每次写入向量库的文档批大小（SiliconFlow embeddings 最大输入32 条）
load_dotenv()
DOC_BATCH_SIZE = int(os.getenv("DOC_BATCH_SIZE", "32"))
OCR_LANG = os.getenv("OCR_LANG", "chi_sim+eng")  # 默认中英文

# 可选:指定 tesseract 可执行文件路径（Windows 常见安装路径示例）
_tcmd_env = os.getenv("TESSERACT_CMD")
if _tcmd_env:
    pytesseract.pytesseract.tesseract_cmd = _tcmd_env
    logger.info(f"使用环境变量 TESSERACT_CMD: {_tcmd_env}")
else:
    # 自动探测常见安装路径（Windows）
    common_paths = [
        r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
    ]
    for p in common_paths:
        try:
            if Path(p).exists():
                pytesseract.pytesseract.tesseract_cmd = p
                logger.info(f"检测到Tesseract安装路径: {p}")
                break
        except Exception:
            pass

# 版本输出移动到配置加载后,以确保最终路径生成


def _normalize_text(text: str) -> str:
    """标准化文本以便简单去重:去除多余空白与控制符"""
    return " ".join((text or "").split())


def _is_near_duplicate(a: str, b: str, threshold: float) -> bool:
    """使用序列相似度做近似去重,避免重复块进入向量库"""
    try:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio() >= threshold
    except Exception:
        return False


def _load_ingestion_config() -> Dict[str, Any]:
    """加载摄取配置.如果YAML不可用或文件缺失,则回退到默认配置"""
    default_cfg: Dict[str, Any] = {
        "general": {
            "persist_directory": settings.CHROMA_PERSIST_DIRECTORY,
            "collection_name": "insurance_documents",
            "write_mode": "append",
            "batch_size": DOC_BATCH_SIZE,
            "embedding_model": "",
            "ocr": {
                "enabled_default": False,
                "lang": OCR_LANG,
                "tesseract_cmd": os.getenv("TESSERACT_CMD", ""),
            },
        },
        "sources": [
            {
                "name": "default",
                "path": "./data/documents/pdfs",
                "document_type": "通用",
                "parser_preference": "auto",
                "ocr": {"enabled": False, "lang": OCR_LANG},
                "chunk": {
                    "token_based": True,
                    "chunk_size": min(settings.CHUNK_SIZE, 256),
                    "chunk_overlap": min(settings.CHUNK_OVERLAP, 32),
                    "separators": ["\n\n", "\n", " ", ""],
                },
                "dedup": {"enabled": True, "method": "sequence_ratio", "threshold": 0.96},
            }
        ],
    }

    cfg_path = Path("app/core/ingestion_config.yml")
    if yaml is None or not cfg_path.exists():
        logger.warning("YAML不可用或配置文件缺失,使用默认摄取配置")
        return default_cfg

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        # 合并默认值
        merged = default_cfg
        merged.update(cfg)
        # 内层合并（general/ocr）
        if "general" in cfg:
            merged["general"].update(cfg["general"] or {})
            if "ocr" in cfg["general"]:
                merged["general"]["ocr"].update(cfg["general"]["ocr"] or {})
        if "sources" in cfg:
            merged["sources"] = cfg["sources"] or default_cfg["sources"]
        # 应用 tesseract_cmd（若存在）,否则保留自动探测/环境变量设置
        tcmd = merged["general"]["ocr"].get("tesseract_cmd") or ""
        if tcmd:
            pytesseract.pytesseract.tesseract_cmd = tcmd
        return merged
    except Exception as e:
        logger.error(f"加载摄取配置失败,回退到默认值: {e}")
        return default_cfg


def get_metadata_from_ai(text_snippet: str) -> Dict[str, Any]:
    """
    使用AI从文档文本片段中提取结构化元数据
    
    Args:
        text_snippet (str): 文档文本片段
        
    Returns:
        Dict[str, Any]: 包含元数据的字典
    """
    try:
        try:
            # 尝试动态导入硅基流动Chat模型；如不可用则回退
            from langchain_community.chat_models import ChatSiliconFlow  # type: ignore
            chat_model = ChatSiliconFlow(
                model=settings.OPENAI_MODEL,  # 使用配置中的模型名
                api_key=os.getenv("SILICONFLOW_API_KEY"),
                temperature=settings.OPENAI_TEMPERATURE
            )
            prompt = DIGITAL_ARCHIVIST_PROMPT.format(
                document_text_snippet=text_snippet
            )
            logger.info("正在调用AI提取文档元数据..")
            response = chat_model.invoke(prompt)
            try:
                metadata = json.loads(response.content)
                logger.info(f"成功提取元数据: {metadata}")
                return metadata
            except json.JSONDecodeError as e:
                logger.error(f"AI返回的不是合法的JSON: {e}")
                return {
                    "document_title": "解析失败",
                    "product_name": "未知",
                    "effective_date": "未知",
                    "document_type": "未知",
                    "error": f"JSON解析错误: {str(e)}"
                }
        except ImportError:
            logger.warning("ChatSiliconFlow不可用,使用回退元数据")
            return {
                "document_title": "自动生成",
                "product_name": "未知",
                "effective_date": "未知",
                "document_type": "PDF"
            }
    except Exception as e:
        logger.error(f"AI元数据提取失败: {e}")
        return {
            "document_title": "提取失败",
            "product_name": "未知",
            "effective_date": "未知",
            "document_type": "未知",
            "error": f"AI调用错误: {str(e)}"
        }


def _build_text_splitter(chunk_cfg: Dict[str, Any]) -> RecursiveCharacterTextSplitter:
    """按配置构建文本分割器"""
    token_based = bool(chunk_cfg.get("token_based", True))
    chunk_size = int(chunk_cfg.get("chunk_size", 256))
    chunk_overlap = int(chunk_cfg.get("chunk_overlap", 32))
    separators = chunk_cfg.get("separators") or ["\n\n", "\n", " ", ""]

    if token_based:
        try:
            splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            logger.info(f"使用token分割器: size={chunk_size}, overlap={chunk_overlap}")
            return splitter
        except Exception:
            logger.info("token分割器不可用,回退字符分割器")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=separators,
    )
    logger.info(f"使用字符分割器: size={chunk_size}, overlap={chunk_overlap}")
    return splitter


def main():
    """
    主函数:执行数据摄取管道的核心逻辑
    """
    logger.info("开始执行数据摄取管道...")
    
    # 加载配置
    cfg = _load_ingestion_config()
    general = cfg.get("general", {})
    sources = cfg.get("sources", [])

    # 启动时输出当前 Tesseract 路径并尝试获取版本，便于排查
    try:
        _current_tcmd = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
        if _current_tcmd:
            logger.info(f"当前Tesseract路径: {_current_tcmd}")
        from pytesseract import get_tesseract_version
        _ver = str(get_tesseract_version())
        logger.info(f"检测到Tesseract版本: {_ver}")
    except Exception as _e:
        logger.warning(f"无法获取Tesseract版本,可能未正确安装或路径不可用: {_e}")

    # 向量库目录/集合/嵌入模型/批大小
    vector_store_path = general.get("persist_directory", settings.CHROMA_PERSIST_DIRECTORY)
    collection_name = general.get("collection_name", "insurance_documents")
    batch_size_cfg = int(general.get("batch_size", DOC_BATCH_SIZE))
    embed_model_override = (general.get("embedding_model") or "").strip()

    # 写入模式
    write_mode = (general.get("write_mode", "append") or "append").lower()
    # 文件名分类规则与类型配置
    classification_cfg = cfg.get("classification", {})
    profiles_cfg = cfg.get("profiles", {})
    
    # 汇总所有待处理文件:按分组读取
    grouped_files: List[Tuple[Dict[str, Any], List[Path]]] = []
    for src in sources:
        src_path = Path(src.get("path", "./data/documents/pdfs"))
        if not src_path.exists():
            logger.warning(f"数据源目录不存在,跳过 {src_path}")
            continue
        files = [p for p in src_path.rglob("*.pdf") if p.is_file()]
        if not files:
            logger.warning(f"分组 {src.get('name')} 在 {src_path} 未找到 PDF 文件")
            continue
        logger.info(f"分组 {src.get('name')} 找到 {len(files)} 个PDF文件")
        grouped_files.append((src, files))
    if not grouped_files:
        logger.error("未找到任何待处理PDF文件.请检查ingestion_config.yml的路径设置")
        return
    
    # 存储所有处理后的文档块
    all_documents = []
    total_pages = 0
    ocr_pages = 0
    total_files = 0
    
    def _page_pixmap_to_image(pix: fitz.Pixmap) -> Image.Image:
        """将 PyMuPDF 的 Pixmap 转为 PIL Image"""
        mode = "RGB" if pix.n < 4 else "RGBA"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        if mode == "RGBA":
            img = img.convert("RGB")
        return img

    # 使用布局解析服务替代传统提取与 OCR 回退
    def parse_documents_with_layout(pdf_file: Path,
                                    source_group: str,
                                    document_type: str,
                                    parser_cfg: Dict[str, Any]) -> List[Document]:
        """基于 DocumentParserService 的布局感知解析，返回语义保留块。"""
        nonlocal total_pages, ocr_pages
        strategy = (parser_cfg.get("strategy") or general.get("parser", {}).get("strategy") or "hi_res")
        engine = (parser_cfg.get("engine") or general.get("parser", {}).get("engine") or "unstructured")
        # 兼容新旧配置：优先读取 languages，其次 ocr_languages
        ocr_lang = (
            parser_cfg.get("languages")
            or general.get("parser", {}).get("languages")
            or general.get("parser", {}).get("ocr_languages")
            or OCR_LANG
        )
        token_chunk_target = int(general.get("parser", {}).get("token_chunk_target", 512))
        token_chunk_max = int(general.get("parser", {}).get("token_chunk_max", 1024))
        chunk_overlap = int(general.get("parser", {}).get("chunk_overlap", 64))
        service = DocumentParserService(
            strategy=str(strategy),
            languages=str(ocr_lang),
            infer_table_structure=True,
            token_chunk_target=token_chunk_target,
            token_chunk_max=token_chunk_max,
            chunk_overlap=chunk_overlap,
            engine=str(engine),
        )
        docs = service.parse_pdf_to_chunks(pdf_file, source_group=source_group, document_type=document_type)
        # 估算页数与 OCR 页（hi_res 内部按需 OCR，无法逐页统计，此处保留总数估计）
        total_pages += 1  # 以文件粒度累加，用于指标展示（避免误导性统计）
        return docs
    
    # 遍历分组及其文件
    global_seen: List[str] = []  # 简单近似去重参照（存储规范化后的文本片段）
    for src_cfg, pdf_files in grouped_files:
        src_name = src_cfg.get("name", "default")
        doc_type = src_cfg.get("document_type", "通用")
        ocr_cfg = src_cfg.get("ocr", {})
        force_ocr = bool(ocr_cfg.get("enabled", False))
        ocr_lang_src = str(ocr_cfg.get("lang", general.get("ocr", {}).get("lang", OCR_LANG)))
        chunk_cfg = src_cfg.get("chunk", {})
        dedup_cfg = src_cfg.get("dedup", {"enabled": True, "method": "sequence_ratio", "threshold": 0.96})
        dedup_enabled = bool(dedup_cfg.get("enabled", True))
        threshold = float(dedup_cfg.get("threshold", 0.96))

        text_splitter = _build_text_splitter(chunk_cfg)

        logger.info(f"开始处理分组 {src_name}（默认类型:{doc_type}, OCR={'on' if force_ocr else 'auto'}）")
        for pdf_file in pdf_files:
            total_files += 1
            logger.info(f"正在处理文件: {pdf_file.name}")
            try:
                # 基于文件名的分类（tk=条款, sms=说明书, flbe=费率/利益）
                selected_group = src_name
                selected_doc_type = doc_type
                selected_ocr_cfg = ocr_cfg
                selected_chunk_cfg = chunk_cfg
                selected_dedup_cfg = dedup_cfg

                patterns = (classification_cfg or {}).get("patterns", {})
                name_lower = pdf_file.name.lower()
                def _match_any(tokens):
                    return any(str(t).lower() in name_lower for tok in (tokens or []) for t in [tok])

                if _match_any(patterns.get("terms")):
                    selected_group = "terms"
                    selected_doc_type = profiles_cfg.get("terms", {}).get("document_type", "条款")
                    selected_ocr_cfg = profiles_cfg.get("terms", {}).get("ocr", selected_ocr_cfg)
                    selected_chunk_cfg = profiles_cfg.get("terms", {}).get("chunk", selected_chunk_cfg)
                    selected_dedup_cfg = profiles_cfg.get("terms", {}).get("dedup", selected_dedup_cfg)
                elif _match_any(patterns.get("manuals")):
                    selected_group = "manuals"
                    selected_doc_type = profiles_cfg.get("manuals", {}).get("document_type", "说明书")
                    selected_ocr_cfg = profiles_cfg.get("manuals", {}).get("ocr", selected_ocr_cfg)
                    selected_chunk_cfg = profiles_cfg.get("manuals", {}).get("chunk", selected_chunk_cfg)
                    selected_dedup_cfg = profiles_cfg.get("manuals", {}).get("dedup", selected_dedup_cfg)
                elif _match_any(patterns.get("tables")):
                    selected_group = "tables"
                    selected_doc_type = profiles_cfg.get("tables", {}).get("document_type", "费率/利益")
                    selected_ocr_cfg = profiles_cfg.get("tables", {}).get("ocr", selected_ocr_cfg)
                    selected_chunk_cfg = profiles_cfg.get("tables", {}).get("chunk", selected_chunk_cfg)
                    selected_dedup_cfg = profiles_cfg.get("tables", {}).get("dedup", selected_dedup_cfg)

                # 解析文档（布局感知）
                parser_cfg = selected_chunk_cfg if isinstance(selected_chunk_cfg, dict) else {}
                documents = parse_documents_with_layout(
                    pdf_file,
                    source_group=selected_group,
                    document_type=selected_doc_type,
                    parser_cfg=profiles_cfg.get(selected_group, {}).get("parser", {})
                    if profiles_cfg else {}
                )
                if not documents:
                    logger.warning(f"文件 {pdf_file.name} 解析失败或为空")
                    continue

                # 取第一块文本作为摘要，用于 AI 元数据提取（跳过表格块）
                first_text_block = next((d for d in documents if d.page_content and not d.metadata.get("table_json_schema")), None)
                first_page_text = (first_text_block.page_content if first_text_block else documents[0].page_content)[:2000]
                ai_metadata = get_metadata_from_ai(first_page_text)

                # 已由布局服务进行一级边界与二级 token 分割，此处不再使用传统 splitter
                document_chunks = documents
                logger.info(f"文件 {pdf_file.name} 解析为 {len(document_chunks)} 个语义块")

                # 去重（按分类配置）
                filtered_chunks = []
                dedup_enabled_file = bool(selected_dedup_cfg.get("enabled", True))
                threshold_file = float(selected_dedup_cfg.get("threshold", 0.96))
                if dedup_enabled_file:
                    seen_local: List[str] = []
                    for ch in document_chunks:
                        txt_norm = _normalize_text(ch.page_content)
                        # 先做精确重复检查
                        if txt_norm in seen_local:
                            continue
                        # 再做近似重复（与已加入块比较）
                        is_dup = any(_is_near_duplicate(txt_norm, prev, threshold_file) for prev in seen_local[-50:])
                        if is_dup:
                            continue
                        seen_local.append(txt_norm)
                        filtered_chunks.append(ch)
                    document_chunks = filtered_chunks
                    logger.info(f"去重后块数: {len(document_chunks)}")

                # 添加/合并元数据（AI 元数据 + 现有）
                for chunk in document_chunks:
                    # 生成稳定 chunk_id: sha1(file_path|page_number|normalized_text)
                    norm_text = _normalize_text(chunk.page_content or "")
                    key = f"{chunk.metadata.get('file_path','')}|{chunk.metadata.get('page_number','')}|{norm_text}"
                    chunk_id = hashlib.sha1(key.encode("utf-8")).hexdigest()
                    chunk.metadata.update({
                        "source_file": pdf_file.name,
                        "file_path": str(pdf_file),
                        "document_type": selected_doc_type,
                        "source_group": selected_group,
                        "chunk_id": chunk_id,
                        **ai_metadata,
                    })

                all_documents.extend(document_chunks)
            except Exception as e:
                logger.error(f"处理文件 {pdf_file.name} 时出错: {e}")
                continue
    
    if not all_documents:
        logger.error("没有成功处理任何文档")
        return

    logger.info(f"总共处理了 {len(all_documents)} 个文档块")

    # 关键词抽取（轻量级、异步、失败不阻塞）
    enable_keywords = os.getenv("ENABLE_KEYWORDS", "1") == "1"
    if enable_keywords:
        logger.info("开始异步关键词抽取（不阻塞，失败忽略）...")
        async def _extract_keywords_for_docs(docs: List[Document], max_keywords: int = 8, timeout_s: float = 8.0, concurrency: int = 6):
            llm = LLMService()
            sem = asyncio.Semaphore(concurrency)
            async def _one(doc: Document):
                text = doc.page_content[:2000]
                try:
                    async with sem:
                        kws = await asyncio.wait_for(llm.extract_keywords(text, max_keywords=max_keywords), timeout=timeout_s)
                        # ChromaDB 元数据字段仅支持原子类型，将列表序列化为 JSON 字符串
                        try:
                            doc.metadata["keywords_json"] = json.dumps(kws, ensure_ascii=False)
                        except Exception:
                            doc.metadata["keywords_json"] = ",".join([str(x) for x in (kws or [])])
                except Exception:
                    # 失败情况下写入空 JSON 数组字符串，避免列表类型导致写入失败
                    doc.metadata.setdefault("keywords_json", "[]")
            await asyncio.gather(*[_one(d) for d in docs], return_exceptions=True)

        try:
            asyncio.run(_extract_keywords_for_docs(all_documents))
            logger.info("关键词抽取阶段已完成（部分失败已忽略）")
        except Exception as e:
            logger.warning(f"关键词抽取阶段出现问题（已忽略，不影响摄取）: {e}")
    
    # 仅准备模式:导出分割/去重后的块与元数据为 JSONL
    prepare_only = os.getenv("PREPARE_ONLY", "0") == "1"
    # 兼容命令行参数: --prepare-only 或 --prepare
    if not prepare_only:
        cli_prepare = any(arg in ("--prepare-only", "--prepare") for arg in sys.argv[1:])
        if cli_prepare:
            prepare_only = True
    if prepare_only:
        export_path = Path("data/processed/chunks.jsonl")
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with export_path.open("w", encoding="utf-8") as f:
            for ch in all_documents:
                # 稳定ID:基于文件路径,页号,规范化文本内容
                norm_text = _normalize_text(ch.page_content or "")
                key = f"{ch.metadata.get('file_path','')}|{ch.metadata.get('page_number','')}|{norm_text}"
                _id = hashlib.sha1(key.encode("utf-8")).hexdigest()
                payload = {
                    "id": _id,
                    "text": ch.page_content,
                    "metadata": ch.metadata,
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        logger.info(f"已导出分割产物到 {export_path},共 {len(all_documents)} 个文档块")
        logger.info("准备阶段完成（PREPARE_ONLY=1）,未进行嵌入与写库")
        return
    
    # 初始化嵌入模型（支持远程/本地，且可被配置覆盖）
    try:
        logger.info("初始化嵌入模型...")
        model_name_cfg = (embed_model_override or settings.OPENAI_EMBEDDING_MODEL or "").strip()
        use_local_env = os.getenv("USE_LOCAL_EMBEDDINGS", "0") == "1"
        use_local_cfg = model_name_cfg.lower().startswith("local:") or model_name_cfg.lower().startswith("hf:") or model_name_cfg.lower().startswith("huggingface:")
        use_local = use_local_env or use_local_cfg

        if use_local:
            # 解析本地模型名称（形式: local:BAAI/bge-m3 或 hf:BAAI/bge-m3）
            local_model = model_name_cfg.split(":", 1)[1] if ":" in model_name_cfg else "BAAI/bge-m3"
            logger.info(f"Embeddings provider: local:huggingface, model={local_model}")
            embeddings = HuggingFaceEmbeddings(
                model_name=local_model,
            )
        else:
            remote_model = model_name_cfg or "BAAI/bge-large-zh-v1.5"
            logger.info(
                f"Embeddings provider: base_url={settings.OPENAI_BASE_URL}, model={remote_model}"
            )
            embeddings = OpenAIEmbeddings(
                api_key=(settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY),
                base_url=(settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL),
                model=remote_model,
                timeout=60,
            )
    except Exception as e:
        logger.error(f"初始化嵌入模型失败: {e}")
        return

    # 构建并持久化 BM25 索引与 chunk 映射（与向量库使用相同的列表与chunk_id）
    try:
        logger.info("开始构建 BM25 索引（BM25Plus + jieba 分词）...")
        bm25_dir = Path("data/processed")
        bm25_dir.mkdir(parents=True, exist_ok=True)

        # 准备 corpus 与 id 映射
        chunk_ids: List[str] = []
        chunk_texts: List[str] = []
        for ch in all_documents:
            cid = ch.metadata.get("chunk_id")
            if not cid:
                # 若缺失则回退生成
                norm_text = _normalize_text(ch.page_content or "")
                key = f"{ch.metadata.get('file_path','')}|{ch.metadata.get('page_number','')}|{norm_text}"
                cid = hashlib.sha1(key.encode("utf-8")).hexdigest()
                ch.metadata["chunk_id"] = cid
            chunk_ids.append(cid)
            chunk_texts.append(ch.page_content or "")

        # 分词（中文优先，兼容英文与符号）
        tokenized_corpus: List[List[str]] = []
        for txt in chunk_texts:
            try:
                tokens = [t.strip() for t in jieba.lcut(_normalize_text(txt)) if t.strip()]
            except Exception:
                # 回退: 按空白分割
                tokens = [t.strip() for t in (_normalize_text(txt).split()) if t.strip()]
            tokenized_corpus.append(tokens)

        bm25_model = BM25Plus(tokenized_corpus)
        bm25_payload = {
            "bm25": bm25_model,
            "ids": chunk_ids,
        }

        with (bm25_dir / "bm25_index.pkl").open("wb") as pf:
            pickle.dump(bm25_payload, pf)
        logger.info("BM25 索引已持久化到 data/processed/bm25_index.pkl")

        # 持久化 chunk_id -> text 映射为 JSON
        chunk_map_path = bm25_dir / "bm25_chunk_map.json"
        with chunk_map_path.open("w", encoding="utf-8") as jf:
            json.dump({chunk_ids[i]: chunk_texts[i] for i in range(len(chunk_ids))}, jf, ensure_ascii=False)
        logger.info("BM25 chunk 映射已持久化到 data/processed/bm25_chunk_map.json")
    except Exception as e:
        logger.warning(f"BM25 索引构建或持久化失败（将继续仅向量流程）: {e}")
    
    # 创建/重建向量数据库目录
    vector_store_dir = Path(vector_store_path)
    rebuild_env = os.getenv("REBUILD_VECTOR_DB", "0") == "1"
    rebuild = rebuild_env or (write_mode == "rebuild")
    if rebuild and vector_store_dir.exists():
        logger.info(f"检测到 REBUILD_VECTOR_DB=1,正在清理旧向量库 {vector_store_dir}")
        try:
            shutil.rmtree(vector_store_dir)
        except Exception as e:
            logger.warning(f"清理旧向量库失败: {e}")
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info("正在创建/打开 ChromaDB 向量数据库...")
        # 使用单例客户端以统一配置,并禁用匿名遥测
        chroma_client = chroma_manager.get_client()
        
        # 初始化空的 Chroma 向量库，然后分批写入，避免一次性大批量嵌入导致 400
        vectorstore = Chroma(
            client=chroma_client,
            embedding_function=embeddings,
            persist_directory=vector_store_path,
            collection_name=collection_name,
        )
        
        # 分批添加文档以控制每次嵌入的输入量
        batch_size = batch_size_cfg
        total = len(all_documents)
        fallback_applied = False
        local_fallback_applied = False
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_docs = all_documents[start:end]
            logger.info(f"写入批次 {start}-{end},共 {len(batch_docs)} 个文档块")
            # 在写入前统一清洗元数据，确保所有值为 Chroma 允许的原子类型
            def _sanitize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
                out: Dict[str, Any] = {}
                for k, v in (md or {}).items():
                    if v is None or isinstance(v, (str, int, float, bool)):
                        out[k] = v
                    elif isinstance(v, (list, dict)):
                        try:
                            out[k] = json.dumps(v, ensure_ascii=False)
                        except Exception:
                            out[k] = str(v)
                    else:
                        out[k] = str(v)
                return out
            for _d in batch_docs:
                try:
                    _d.metadata = _sanitize_metadata(getattr(_d, "metadata", {}) or {})
                except Exception:
                    pass
            try:
                # 使用稳定 chunk_id 作为向量库的 ids，确保与BM25一致
                ids = [doc.metadata.get("chunk_id") or "" for doc in batch_docs]
                vectorstore.add_documents(batch_docs, ids=ids)
            except Exception as e:
                msg = str(e)
                # 针对 BGE 大模型的 512 token 输入限制,切换到 bge-m3 作为兜底
                if ("less than 512 tokens" in msg or "maximum context length" in msg) and not fallback_applied and not use_local:
                    logger.warning("检测到输入超过 512 tokens,切换到 BAAI/bge-m3 继续写入")
                    embeddings = OpenAIEmbeddings(
                        api_key=(settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY),
                        base_url=(settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL),
                        model="BAAI/bge-m3",
                        timeout=60,
                    )
                    vectorstore = Chroma(
                        client=chroma_client,
                        embedding_function=embeddings,
                        persist_directory=vector_store_path,
                        collection_name=collection_name,
                    )
                    fallback_applied = True
                    for _d in batch_docs:
                        try:
                            _d.metadata = _sanitize_metadata(getattr(_d, "metadata", {}) or {})
                        except Exception:
                            pass
                    vectorstore.add_documents(batch_docs)
                # 针对外部服务的限制或网络问题，自动回退到本地嵌入以继续
                elif ("429" in msg or "Too Many Requests" in msg or "timed out" in msg or "Timeout" in msg or "SSL" in msg or "Connection" in msg or "HTTP" in msg) and not local_fallback_applied:
                    logger.warning("检测到外部嵌入服务问题，自动回退到本地 HuggingFace 嵌入继续写入")
                    try:
                        hf_model = (embed_model_override.split(":", 1)[1] if (embed_model_override and ":" in embed_model_override) else "BAAI/bge-m3")
                        embeddings = HuggingFaceEmbeddings(model_name=hf_model)
                        vectorstore = Chroma(
                            client=chroma_client,
                            embedding_function=embeddings,
                            persist_directory=vector_store_path,
                            collection_name=collection_name,
                        )
                        local_fallback_applied = True
                        for _d in batch_docs:
                            try:
                                _d.metadata = _sanitize_metadata(getattr(_d, "metadata", {}) or {})
                            except Exception:
                                pass
                        vectorstore.add_documents(batch_docs)
                    except Exception as e2:
                        logger.error(f"本地嵌入回退失败: {e2}")
                        raise
                else:
                    raise
        
        # 持久化说明: 在指定 persist_directory 时，langchain_chroma 的 Chroma 会自动持久化
        # 因此无需显式调用 persist()
        logger.info(f"成功创建/更新向量数据库,存储路径: {vector_store_path}")
        logger.info(f"数据库本次写入 {len(all_documents)} 个文档块,处理 {total_files} 个文件")
        logger.info(f"文本页总数: {total_pages},其中 OCR 页数: {ocr_pages}")

        # 在向量库构建完成后，将结构化元数据持久化到 SQL 表 document_metadata
        try:
            logger.info("开始持久化结构化元数据到 SQL 表 document_metadata...")
            asyncio.run(_persist_structured_metadata(all_documents))
            logger.info("结构化元数据持久化完成")
        except Exception as e:
            logger.warning(f"结构化元数据持久化失败: {e}")
        
        # 验证数据库（如果集合可用）
        try:
            collection = vectorstore._collection  # type: ignore[attr-defined]
            size = collection.count() if hasattr(collection, "count") else "unknown"
            logger.info(f"向量数据库验证 - 集合大小: {size}")
        except Exception as e:
            logger.warning(f"向量数据库验证阶段出现问题（不影响持久化）: {e}")
        
    except Exception as e:
        logger.error(f"创建向量数据库失败: {e}")
        return
    
    logger.info("数据摄取管道执行完成")


if __name__ == "__main__":
    main()


async def _persist_structured_metadata(all_documents):
    """将文档块的结构化元数据写入 SQL 表 document_metadata。

    期望从每个文档块中提取如下字段：
    - chunk_id
    - product_name
    - effective_date
    - document_type
    - status
    若缺失则跳过该条（至少需要 chunk_id）。
    """
    try:
        # 确保表结构已创建
        await init_db()

        # 创建异步会话
        session = await db_manager.create_session()
        inserted = 0

        from sqlalchemy import select

        for ch in (all_documents or []):
            try:
                meta = getattr(ch, "metadata", None)
                if meta is None:
                    meta = ch.get("metadata") if isinstance(ch, dict) else {}

                chunk_id = meta.get("chunk_id") if isinstance(meta, dict) else None
                if not chunk_id:
                    # 若缺失则回退生成
                    norm_text = _normalize_text(getattr(ch, "page_content", "") or (ch.get("page_content") if isinstance(ch, dict) else ""))
                    key = f"{(meta.get('file_path') if isinstance(meta, dict) else '')}|{(meta.get('page_number') if isinstance(meta, dict) else '')}|{norm_text}"
                    chunk_id = hashlib.sha1(key.encode("utf-8")).hexdigest()

                product_name = (meta.get("product_name") if isinstance(meta, dict) else None) or (meta.get("plan_name") if isinstance(meta, dict) else None)
                effective_date = (meta.get("effective_date") if isinstance(meta, dict) else None) or (meta.get("effective") if isinstance(meta, dict) else None)
                document_type = (meta.get("document_type") if isinstance(meta, dict) else None) or (meta.get("doc_type") if isinstance(meta, dict) else None)
                status = (meta.get("status") if isinstance(meta, dict) else None) or "active"

                # 去重：若 chunk_id 已存在则跳过
                exists = (
                    await session.execute(
                        select(DocumentMetadata).where(DocumentMetadata.chunk_id == str(chunk_id))
                    )
                ).scalar_one_or_none()
                if exists:
                    continue

                record = DocumentMetadata(
                    chunk_id=str(chunk_id),
                    product_name=str(product_name) if product_name else None,
                    effective_date=str(effective_date) if effective_date else None,
                    document_type=str(document_type) if document_type else None,
                    status=str(status) if status else None,
                )
                session.add(record)
                inserted += 1
            except Exception:
                # 单条失败不影响整体
                continue

        await session.commit()
        await db_manager.close_session(session)
        logging.getLogger(__name__).info(f"document_metadata 新增 {inserted} 条记录")
    except Exception as e:
        logging.getLogger(__name__).warning(f"结构化元数据写入失败: {e}")


