"""
文档管理API端点
"""

import json
import os
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.database_models import Document
from app.models.schemas import (
    DocumentResponse, FileUploadResponse, ProcessingStatus, 
    DocumentUpdate, ErrorResponse
)
from app.services.document_service import DocumentService

logger = get_logger(__name__)
router = APIRouter()


@router.post("/upload", response_model=FileUploadResponse, summary="上传PDF文档")
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    上传PDF或TXT文档
    支持的文件格式：PDF, TXT
    文件大小限制：50MB
    """
    try:
        # 验证文件类型
        allowed_extensions = ['.pdf', '.txt']
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(status_code=400, detail="只支持PDF和TXT文件格式")
        
        # 验证文件大小（50MB限制）
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:  # 50MB
            raise HTTPException(status_code=400, detail="文件大小不能超过50MB")
        
        # 重置文件指针
        await file.seek(0)
        
        # 初始化文档服务
        doc_service = DocumentService()
        
        # 保存文件
        file_path, file_hash = await doc_service.save_uploaded_file(file_content, file.filename)
        
        # 检查文件是否已存在
        existing_doc = doc_service.get_document_by_hash(db, file_hash)
        if existing_doc:
            return FileUploadResponse(
                message="文件已存在",
                document_id=existing_doc.id,
                filename=existing_doc.original_filename,
                file_size=existing_doc.file_size,
                upload_time=existing_doc.upload_time,
                processing_status=existing_doc.processing_status
            )
        
        # 创建文档记录
        document = Document(
            filename=os.path.basename(file_path),
            original_filename=file.filename,
            file_path=file_path,
            file_size=len(file_content),
            file_hash=file_hash,
            mime_type=file.content_type or ("text/plain" if file.filename.lower().endswith('.txt') else "application/pdf")
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # 添加后台任务处理文档
        background_tasks.add_task(process_document_background, document.id, request)
        
        logger.info(f"文档上传成功: {file.filename}, ID: {document.id}")
        
        return FileUploadResponse(
            message="文件上传成功，正在处理中",
            document_id=document.id,
            filename=file.filename,
            file_size=len(file_content),
            upload_time=document.upload_time,
            processing_status="pending"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文档上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")


async def process_document_background(document_id: int, request: Request):
    """后台处理文档任务"""
    try:
        from app.core.database import SessionLocal
        
        db = SessionLocal()
        doc_service = DocumentService()
        
        # 处理文档
        success = await doc_service.process_document(db, document_id)
        
        if success:
            # 添加到向量数据库
            vector_service = request.app.state.vector_service
            await vector_service.add_document_chunks(db, document_id)
            logger.info(f"文档处理完成: {document_id}")
        else:
            logger.error(f"文档处理失败: {document_id}")
        
        db.close()
        
    except Exception as e:
        logger.error(f"后台文档处理失败: {e}")


@router.get("/", response_model=List[DocumentResponse], summary="获取文档列表")
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取文档列表
    支持分页和状态过滤
    """
    try:
        query = db.query(Document)
        
        if status:
            query = query.filter(Document.processing_status == status)
        
        documents = query.offset(skip).limit(limit).all()
        
        return [
            DocumentResponse(
                id=doc.id,
                filename=doc.filename,
                original_filename=doc.original_filename,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                file_hash=doc.file_hash,
                upload_time=doc.upload_time,
                processed_time=doc.processed_time,
                is_processed=doc.is_processed,
                processing_status=doc.processing_status,
                error_message=doc.error_message,
                metadata=json.loads(doc.metadata_json) if doc.metadata_json else None
            )
            for doc in documents
        ]
        
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取文档列表失败")


@router.get("/{document_id}", response_model=DocumentResponse, summary="获取文档详情")
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """获取指定文档的详细信息"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return DocumentResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_size=document.file_size,
            mime_type=document.mime_type,
            file_hash=document.file_hash,
            upload_time=document.upload_time,
            processed_time=document.processed_time,
            is_processed=document.is_processed,
            processing_status=document.processing_status,
            error_message=document.error_message,
            metadata=json.loads(document.metadata_json) if document.metadata_json else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取文档详情失败")


@router.get("/{document_id}/status", response_model=ProcessingStatus, summary="获取文档处理状态")
async def get_document_status(document_id: int, db: Session = Depends(get_db)):
    """获取文档处理状态"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 计算处理进度
        progress = None
        if document.processing_status == "pending":
            progress = 0.0
        elif document.processing_status == "processing":
            progress = 50.0
        elif document.processing_status == "completed":
            progress = 100.0
        elif document.processing_status == "failed":
            progress = 0.0
        
        # 统计生成的文档块数量
        from app.models.database_models import DocumentChunk
        chunks_created = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).count()
        
        return ProcessingStatus(
            document_id=document.id,
            filename=document.original_filename,
            status=document.processing_status,
            progress=progress,
            error_message=document.error_message,
            chunks_created=chunks_created if chunks_created > 0 else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档处理状态失败: {e}")
        raise HTTPException(status_code=500, detail="获取文档处理状态失败")


@router.put("/{document_id}", response_model=DocumentResponse, summary="更新文档信息")
async def update_document(
    document_id: int,
    document_update: DocumentUpdate,
    db: Session = Depends(get_db)
):
    """更新文档信息"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 更新字段
        if document_update.is_processed is not None:
            document.is_processed = document_update.is_processed
        
        if document_update.processing_status is not None:
            document.processing_status = document_update.processing_status
        
        if document_update.error_message is not None:
            document.error_message = document_update.error_message
        
        if document_update.metadata is not None:
            document.metadata = str(document_update.metadata)
        
        db.commit()
        db.refresh(document)
        
        logger.info(f"文档更新成功: {document_id}")
        
        return DocumentResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_size=document.file_size,
            mime_type=document.mime_type,
            file_hash=document.file_hash,
            upload_time=document.upload_time,
            processed_time=document.processed_time,
            is_processed=document.is_processed,
            processing_status=document.processing_status,
            error_message=document.error_message,
            metadata=eval(document.metadata) if document.metadata else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新文档失败: {e}")
        raise HTTPException(status_code=500, detail="更新文档失败")


@router.delete("/{document_id}", summary="删除文档")
async def delete_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """删除文档及其相关数据"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 删除向量数据
        vector_service = request.app.state.vector_service
        await vector_service.delete_document_vectors(db, document_id)
        
        # 删除文档
        doc_service = DocumentService()
        success = doc_service.delete_document(db, document_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="删除文档失败")
        
        logger.info(f"文档删除成功: {document_id}")
        
        return {"message": "文档删除成功", "document_id": document_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail="删除文档失败")


@router.post("/{document_id}/reprocess", summary="重新处理文档")
async def reprocess_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    """重新处理文档"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 重置处理状态
        document.processing_status = "pending"
        document.is_processed = False
        document.error_message = None
        document.processed_time = None
        
        # 删除现有的文档块
        from app.models.database_models import DocumentChunk
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        
        # 删除向量数据
        vector_service = request.app.state.vector_service
        await vector_service.delete_document_vectors(db, document_id)
        
        db.commit()
        
        # 添加后台任务重新处理
        background_tasks.add_task(process_document_background, document_id, request)
        
        logger.info(f"文档重新处理开始: {document_id}")
        
        return {"message": "文档重新处理已开始", "document_id": document_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理文档失败: {e}")
        raise HTTPException(status_code=500, detail="重新处理文档失败")


@router.get("/{document_id}/chunks", summary="获取文档块")
async def get_document_chunks(
    document_id: int,
    db: Session = Depends(get_db)
):
    """获取指定文档的所有块"""
    try:
        # 检查文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 获取文档块
        from app.models.database_models import DocumentChunk
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()
        
        return [
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "content_hash": chunk.content_hash,
                "vector_id": chunk.vector_id,
                "created_time": chunk.created_time
            }
            for chunk in chunks
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档块失败: {e}")
        raise HTTPException(status_code=500, detail="获取文档块失败")