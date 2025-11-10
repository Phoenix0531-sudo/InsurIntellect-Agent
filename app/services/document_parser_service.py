"""
DocumentParserService
基于 unstructured 的布局感知解析服务：
- 使用 partition_pdf(strategy="hi_res") 进行版面解析
- 生成语义保留的块（标题、段落、列表、表格）
- 表格同时输出 Markdown（供 LLM 上下文）与 JSON（供系统元数据过滤）
"""

from typing import List, Dict, Any, Optional, Tuple
import os
from pathlib import Path

try:
    # LangChain Document 类型（向后兼容）
    from langchain_core.documents import Document  # type: ignore
except Exception:
    from langchain.schema import Document  # type: ignore

from app.core.app_logging import get_logger

logger = get_logger(__name__)


class DocumentParserService:
    def __init__(self,
                 strategy: str = "hi_res",
                 languages: Optional[str] = None,
                 ocr_languages: Optional[str] = "chi_sim+eng",
                 infer_table_structure: bool = True,
                 token_chunk_target: int = 512,
                 token_chunk_max: int = 1024,
                 chunk_overlap: int = 64,
                 engine: str = "unstructured"):
        self.strategy = strategy
        # 兼容旧配置：优先使用 languages，其次使用 ocr_languages（已弃用）
        self.languages = (languages or ocr_languages or "chi_sim+eng")
        self.infer_table_structure = infer_table_structure
        self.token_chunk_target = token_chunk_target
        self.token_chunk_max = token_chunk_max
        self.chunk_overlap = chunk_overlap
        self.engine = (engine or "unstructured").lower()

    def _token_split(self, text: str) -> List[str]:
        """二级分割：基于 token 的长度控制。
        优先使用 tiktoken；若不可用，退化为按字符近似分割。
        """
        if not text:
            return []
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore
            splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                chunk_size=self.token_chunk_target,
                chunk_overlap=min(self.chunk_overlap, self.token_chunk_target // 8) or 0,
            )
            # 直接对字符串进行 split_text
            return splitter.split_text(text)
        except Exception:
            # 简化字符级分割：按近似 token（4 字符≈1 token）
            approx_token = max(self.token_chunk_target * 4, 1)
            overlap_chars = max(min(self.chunk_overlap * 4, approx_token // 8), 0)
            chunks: List[str] = []
            i = 0
            while i < len(text):
                end = min(i + approx_token, len(text))
                chunks.append(text[i:end])
                if end >= len(text):
                    break
                i = max(end - overlap_chars, i + 1)
            return chunks

    def _get_bbox(self, element: Any) -> Optional[Tuple[float, float, float, float]]:
        """提取元素的边界框 (x0, y0, x1, y1)。"""
        try:
            md = getattr(element, "metadata", None)
            coords = getattr(md, "coordinates", None)
            if coords and getattr(coords, "points", None):
                # points: [(x0,y0), (x1,y0), (x1,y1), (x0,y1)]
                pts = coords.points  # type: ignore
                if isinstance(pts, list) and len(pts) >= 4:
                    x0, y0 = pts[0]
                    x1, y1 = pts[2]
                    return float(x0), float(y0), float(x1), float(y1)
        except Exception:
            pass
        return None

    def _table_html_to_rows(self, html: str) -> List[List[str]]:
        """将 HTML 表格转换为二维行列文本。"""
        rows: List[List[str]] = []
        if not html:
            return rows
        try:
            from bs4 import BeautifulSoup  # type: ignore
            soup = BeautifulSoup(html, "html.parser")
            for tr in soup.find_all("tr"):
                row: List[str] = []
                for cell in tr.find_all(["td", "th"]):
                    txt = (cell.get_text(separator=" ") or "").strip()
                    row.append(txt)
                if row:
                    rows.append(row)
            return rows
        except Exception:
            # 朴素回退：非常简化的解析，不保证所有嵌套结构
            import re
            tr_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S)
            for tr in tr_blocks:
                cells = re.findall(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", tr, flags=re.I | re.S)
                cleaned = [re.sub(r"<[^>]+>", " ", c).strip() for c in cells]
                if cleaned:
                    rows.append(cleaned)
            return rows

    def _rows_to_markdown(self, rows: List[List[str]]) -> str:
        """将二维行列转换为 Markdown 表格。如果没有行，返回空字符串。"""
        if not rows:
            return ""
        # 处理头部
        header = rows[0]
        md = "| " + " | ".join(h.strip() or " " for h in header) + " |\n"
        md += "| " + " | ".join(["---" for _ in header]) + " |\n"
        for row in rows[1:]:
            md += "| " + " | ".join((c.strip() if isinstance(c, str) else str(c)) for c in row) + " |\n"
        return md.strip()

    def parse_pdf_to_chunks(self, pdf_path: Path, source_group: str, document_type: str) -> List[Document]:
        """解析 PDF 并返回语义保留的 Document 列表（每个元素或表格为一个基础块，随后做二级 token 分割）。"""
        # 若明确选择非 unstructured 引擎，则直接回退
        if self.engine != "unstructured":
            return self._fallback_parse_pdf(pdf_path, source_group, document_type)
        try:
            from unstructured.partition.pdf import partition_pdf  # type: ignore
        except Exception as e:
            logger.warning(f"未安装 unstructured 解析库，使用回退解析: {e}")
            return self._fallback_parse_pdf(pdf_path, source_group, document_type)

        elements = []
        try:
            elements = partition_pdf(
                filename=str(pdf_path),
                strategy=self.strategy,
                languages=self.languages,
                infer_table_structure=self.infer_table_structure,
                include_page_breaks=True,
            )
        except Exception as e:
            logger.warning(f"partition_pdf 解析失败，使用回退解析: {e}")
            return self._fallback_parse_pdf(pdf_path, source_group, document_type)

        # 排序：按页、按 y0、再按 x0，尽量维持阅读顺序（hi_res 已内置列检测能力）
        def _sort_key(el: Any):
            pn = getattr(getattr(el, "metadata", None), "page_number", 0) or 0
            bbox = self._get_bbox(el) or (0.0, 0.0, 0.0, 0.0)
            return (int(pn), float(bbox[1]), float(bbox[0]))

        elements = sorted(elements, key=_sort_key)

        docs: List[Document] = []
        for el in elements:
            el_type = getattr(el, "category", None) or getattr(el, "type", None) or "Unknown"
            text = getattr(el, "text", "") or ""
            md = getattr(el, "metadata", None)
            page_number = getattr(md, "page_number", None)
            bbox = self._get_bbox(el)

            base_meta: Dict[str, Any] = {
                "source_file": pdf_path.name,
                "file_path": str(pdf_path),
                "page_number": page_number,
                "layout_type": el_type,
                "bbox": bbox,
                "source_group": source_group,
                "document_type": document_type,
            }

            if el_type.lower() == "table":
                # 表格：生成 Markdown 内容 + JSON 行列结构
                table_html = None
                try:
                    table_html = getattr(md, "text_as_html", None)
                except Exception:
                    table_html = None

                rows: List[List[str]] = []
                if table_html:
                    rows = self._table_html_to_rows(table_html)
                markdown = self._rows_to_markdown(rows)
                json_schema: Dict[str, Any] = {"rows": rows, "has_header": True if rows else False}

                # 如果 partition 返回了 text，则优先使用 markdown；否则退回 text
                content = markdown or (text or "")
                # 二级分割不应用于表格（保持整体结构），但过大时仍可切分
                if content and len(content) > self.token_chunk_max * 4:
                    for sub in self._token_split(content):
                        docs.append(Document(page_content=sub, metadata={**base_meta, "table_json_schema": json_schema}))
                else:
                    docs.append(Document(page_content=content, metadata={**base_meta, "table_json_schema": json_schema}))
                continue

            # 非表格：标题、段落、列表、文本
            if not text:
                # 空文本元素跳过
                continue

            # 一级边界：以元素为单位；二级分割：token 控制在目标范围
            for sub in self._token_split(text):
                docs.append(Document(page_content=sub, metadata=base_meta))

        logger.info(f"布局解析完成: {pdf_path.name}, 生成基础块 {len(docs)}")
        return docs

    def _fallback_parse_pdf(self, pdf_path: Path, source_group: str, document_type: str) -> List[Document]:
        """当 unstructured 无法使用时的回退解析：使用 PyPDF2/pypdf 逐页提取文本并进行二级 token 分割。"""
        try:
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except Exception:
                from pypdf import PdfReader  # type: ignore
        except Exception as e:
            logger.error(f"未安装 PDF 解析后备库: {e}")
            return []

        docs: List[Document] = []
        try:
            reader = PdfReader(str(pdf_path))
            for i, page in enumerate(getattr(reader, "pages", []), start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if not text.strip():
                    # 尝试使用 PyMuPDF 文本提取作为第一回退
                    try:
                        import fitz  # type: ignore
                        with fitz.open(str(pdf_path)) as doc:
                            if i - 1 < doc.page_count:
                                page_obj = doc.load_page(i - 1)
                                text = page_obj.get_text("text") or ""
                    except Exception:
                        text = text or ""
                    # 若仍为空，进行 OCR 回退（适用于扫描版 PDF）
                    if not text.strip():
                        try:
                            import fitz  # type: ignore
                            import pytesseract  # type: ignore
                            from PIL import Image  # type: ignore

                            tcmd = os.getenv("TESSERACT_CMD", "").strip()
                            if tcmd:
                                try:
                                    pytesseract.pytesseract.tesseract_cmd = tcmd
                                except Exception:
                                    pass

                            with fitz.open(str(pdf_path)) as doc:
                                if i - 1 < doc.page_count:
                                    page_obj = doc.load_page(i - 1)
                                    pix = page_obj.get_pixmap(matrix=fitz.Matrix(2, 2))
                                    mode = "RGB" if pix.n < 4 else "RGBA"
                                    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                                    if mode == "RGBA":
                                        img = img.convert("RGB")
                                    # OCR 语言配置（如 chi_sim+eng）
                                    ocr_lang = (self.languages or "chi_sim+eng").strip()
                                    try:
                                        text = pytesseract.image_to_string(img, lang=ocr_lang) or ""
                                    except Exception:
                                        text = ""
                        except Exception:
                            text = text or ""
                    if not text.strip():
                        continue
                base_meta = {
                    "source_file": pdf_path.name,
                    "file_path": str(pdf_path),
                    "page_number": i,
                    "layout_type": "page_text" if text else "ocr_text",
                    "bbox": None,
                    "source_group": source_group,
                    "document_type": document_type,
                }
                for sub in self._token_split(text):
                    docs.append(Document(page_content=sub, metadata=base_meta))

            if docs:
                logger.info(f"回退解析完成: {pdf_path.name}, 生成基础块 {len(docs)}")
            else:
                logger.warning(f"回退解析失败或为空: {pdf_path.name}")
            return docs
        except Exception as e:
            logger.error(f"回退 PDF 解析异常: {e}")
            return []
