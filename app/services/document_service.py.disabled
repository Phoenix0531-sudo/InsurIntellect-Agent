"""
文档处理服务
负责PDF文档的上传、解析、分块等处理
"""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import PyPDF2
import pdfplumber
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database_models import Document, DocumentChunk
from app.models.schemas import DocumentCreate, DocumentChunkCreate

logger = get_logger(__name__)


class DocumentService:
    """文档处理服务类"""
    
    def __init__(self):
        self.pdf_storage_path = Path(settings.PDF_STORAGE_PATH)
        self.processed_data_path = Path(settings.PROCESSED_DATA_PATH)
        
        # 确保目录存在
        self.pdf_storage_path.mkdir(parents=True, exist_ok=True)
        self.processed_data_path.mkdir(parents=True, exist_ok=True)
    
    def calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    async def save_uploaded_file(self, file_content: bytes, filename: str) -> Tuple[str, str]:
        """保存上传的文件"""
        try:
            # 生成唯一文件名
            file_hash = hashlib.sha256(file_content).hexdigest()
            file_extension = Path(filename).suffix
            unique_filename = f"{file_hash}{file_extension}"
            file_path = self.pdf_storage_path / unique_filename
            
            # 保存文件
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            logger.info(f"文件保存成功: {filename} -> {unique_filename}")
            return str(file_path), file_hash
            
        except Exception as e:
            logger.error(f"文件保存失败: {e}")
            raise
    
    def extract_text_from_pdf(self, file_path: str) -> List[Tuple[str, int]]:
        """从PDF或TXT文件提取文本，返回(文本内容, 页码)的列表"""
        text_pages = []
        
        try:
            # 检查文件扩展名
            file_extension = Path(file_path).suffix.lower()
            
            if file_extension == '.txt':
                # 处理TXT文件
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    if content.strip():
                        text_pages.append((content.strip(), 1))
                logger.info(f"从TXT文件提取文本成功，共1页")
                return text_pages
            
            # 处理PDF文件
            # 首先尝试使用pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text and text.strip():
                        text_pages.append((text.strip(), page_num))
            
            if not text_pages:
                # 如果pdfplumber没有提取到文本，尝试PyPDF2
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num, page in enumerate(pdf_reader.pages, 1):
                        text = page.extract_text()
                        if text and text.strip():
                            text_pages.append((text.strip(), page_num))
            
            logger.info(f"从PDF提取文本成功，共{len(text_pages)}页")
            return text_pages
            
        except Exception as e:
            logger.error(f"文本提取失败: {e}")
            raise
    
    def split_text_into_chunks(self, text_pages: List[Tuple[str, int]]) -> List[dict]:
        """将文本分割成块"""
        chunks = []
        chunk_index = 0
        
        for text, page_num in text_pages:
            # 改进的分块策略：确保每个块都不超过最大长度
            paragraphs = text.split('\n\n')
            current_chunk = ""
            start_char = 0
            
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                
                # 如果段落本身就超过最大长度，需要进一步分割
                if len(paragraph) > settings.CHUNK_SIZE:
                    # 先保存当前块（如果有内容）
                    if current_chunk:
                        chunk_data = {
                            'chunk_index': chunk_index,
                            'content': current_chunk.strip(),
                            'page_number': page_num,
                            'start_char': start_char,
                            'end_char': start_char + len(current_chunk)
                        }
                        chunks.append(chunk_data)
                        chunk_index += 1
                        current_chunk = ""
                    
                    # 将长段落按句子分割
                    sentences = paragraph.split('。')
                    temp_chunk = ""
                    
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        
                        # 添加句号（除了最后一个句子）
                        if sentence != sentences[-1]:
                            sentence += "。"
                        
                        # 如果添加这个句子会超过限制
                        if len(temp_chunk) + len(sentence) > settings.CHUNK_SIZE and temp_chunk:
                            chunk_data = {
                                'chunk_index': chunk_index,
                                'content': temp_chunk.strip(),
                                'page_number': page_num,
                                'start_char': start_char,
                                'end_char': start_char + len(temp_chunk)
                            }
                            chunks.append(chunk_data)
                            chunk_index += 1
                            
                            # 处理重叠
                            overlap_text = temp_chunk[-settings.CHUNK_OVERLAP:] if len(temp_chunk) > settings.CHUNK_OVERLAP else temp_chunk
                            temp_chunk = overlap_text + " " + sentence
                            start_char = start_char + len(temp_chunk) - len(overlap_text) - len(sentence) - 1
                        else:
                            if temp_chunk:
                                temp_chunk += " " + sentence
                            else:
                                temp_chunk = sentence
                    
                    # 保存剩余的临时块
                    if temp_chunk.strip():
                        current_chunk = temp_chunk
                    
                else:
                    # 如果当前块加上新段落超过最大长度，则创建新块
                    if len(current_chunk) + len(paragraph) > settings.CHUNK_SIZE and current_chunk:
                        chunk_data = {
                            'chunk_index': chunk_index,
                            'content': current_chunk.strip(),
                            'page_number': page_num,
                            'start_char': start_char,
                            'end_char': start_char + len(current_chunk)
                        }
                        chunks.append(chunk_data)
                        chunk_index += 1
                        
                        # 处理重叠
                        overlap_text = current_chunk[-settings.CHUNK_OVERLAP:] if len(current_chunk) > settings.CHUNK_OVERLAP else current_chunk
                        current_chunk = overlap_text + " " + paragraph
                        start_char = start_char + len(current_chunk) - len(overlap_text) - len(paragraph) - 1
                    else:
                        if current_chunk:
                            current_chunk += " " + paragraph
                        else:
                            current_chunk = paragraph
            
            # 添加最后一个块
            if current_chunk.strip():
                chunk_data = {
                    'chunk_index': chunk_index,
                    'content': current_chunk.strip(),
                    'page_number': page_num,
                    'start_char': start_char,
                    'end_char': start_char + len(current_chunk)
                }
                chunks.append(chunk_data)
                chunk_index += 1
        
        logger.info(f"文本分块完成，共生成{len(chunks)}个块")
        return chunks
    
    async def process_document(self, db: Session, document_id: int) -> bool:
        """处理文档：提取文本并分块"""
        try:
            # 获取文档记录
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                logger.error(f"文档不存在: {document_id}")
                return False
            
            # 更新处理状态
            document.processing_status = "processing"
            db.commit()
            
            # 提取文本
            text_pages = self.extract_text_from_pdf(document.file_path)
            if not text_pages:
                document.processing_status = "failed"
                document.error_message = "无法从PDF提取文本"
                db.commit()
                return False
            
            # 分块
            chunks_data = self.split_text_into_chunks(text_pages)
            
            # 保存文档块到数据库
            for chunk_data in chunks_data:
                content_hash = hashlib.sha256(chunk_data['content'].encode()).hexdigest()
                
                chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk_data['chunk_index'],
                    content=chunk_data['content'],
                    content_hash=content_hash,
                    page_number=chunk_data['page_number'],
                    start_char=chunk_data['start_char'],
                    end_char=chunk_data['end_char']
                )
                db.add(chunk)
            
            # 更新文档状态
            document.is_processed = True
            document.processing_status = "completed"
            document.processed_time = datetime.utcnow()
            db.commit()
            
            logger.info(f"文档处理完成: {document.filename}, 生成{len(chunks_data)}个块")
            return True
            
        except Exception as e:
            logger.error(f"文档处理失败: {e}")
            if 'document' in locals():
                document.processing_status = "failed"
                document.error_message = str(e)
                db.commit()
            return False
    
    def get_document_by_hash(self, db: Session, file_hash: str) -> Optional[Document]:
        """根据文件哈希获取文档"""
        return db.query(Document).filter(Document.file_hash == file_hash).first()
    
    def get_document_chunks(self, db: Session, document_id: int) -> List[DocumentChunk]:
        """获取文档的所有块"""
        return db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index).all()
    
    def delete_document(self, db: Session, document_id: int) -> bool:
        """删除文档及其相关数据"""
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                return False
            
            # 删除物理文件
            if os.path.exists(document.file_path):
                os.remove(document.file_path)
            
            # 删除数据库记录（级联删除会自动删除相关的chunks）
            db.delete(document)
            db.commit()
            
            logger.info(f"文档删除成功: {document.filename}")
            return True
            
        except Exception as e:
            logger.error(f"文档删除失败: {e}")
            db.rollback()
            return False