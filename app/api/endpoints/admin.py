"""
管理员API端点
"""

import os
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.database import get_db
from app.core.app_logging import get_logger
from app.core.config import settings
from app.models.database_models import Document, DocumentChunk, QueryHistory, SystemMetrics
from app.models.schemas import (
    HealthCheck, SystemStats, ErrorResponse
)

logger = get_logger(__name__)
router = APIRouter()


@router.get("/system/info", summary="获取系统信息")
async def get_system_info(request: Request):
    """获取系统基本信息"""
    try:
        import psutil
        import platform
        
        # 获取系统信息
        system_info = {
            "system": {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version()
            },
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "percent": psutil.virtual_memory().percent,
                "used": psutil.virtual_memory().used,
                "free": psutil.virtual_memory().free
            },
            "disk": {
                "total": psutil.disk_usage('/').total,
                "used": psutil.disk_usage('/').used,
                "free": psutil.disk_usage('/').free,
                "percent": psutil.disk_usage('/').percent
            },
            "cpu": {
                "physical_cores": psutil.cpu_count(logical=False),
                "total_cores": psutil.cpu_count(logical=True),
                "max_frequency": psutil.cpu_freq().max if psutil.cpu_freq() else None,
                "min_frequency": psutil.cpu_freq().min if psutil.cpu_freq() else None,
                "current_frequency": psutil.cpu_freq().current if psutil.cpu_freq() else None,
                "cpu_usage": psutil.cpu_percent(interval=1)
            },
            "application": {
                "name": "InsurIntellect Agent",
                "version": "1.0.0",
                "environment": settings.ENVIRONMENT,
                "debug_mode": settings.DEBUG,
                "log_level": settings.LOG_LEVEL
            }
        }
        
        return system_info
        
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取系统信息失败")


@router.get("/system/metrics", summary="获取系统指标")
async def get_system_metrics(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """获取系统性能指标"""
    try:
        # 计算时间范围
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # 查询系统指标
        metrics = db.query(SystemMetrics).filter(
            SystemMetrics.timestamp >= start_time,
            SystemMetrics.timestamp <= end_time
        ).order_by(desc(SystemMetrics.timestamp)).all()
        
        if not metrics:
            return {
                "message": "暂无系统指标数据",
                "time_range": {
                    "start": start_time,
                    "end": end_time,
                    "hours": hours
                },
                "metrics": []
            }
        
        # 格式化指标数据
        formatted_metrics = []
        for metric in metrics:
            formatted_metrics.append({
                "timestamp": metric.timestamp,
                "cpu_usage": metric.cpu_usage,
                "memory_usage": metric.memory_usage,
                "disk_usage": metric.disk_usage,
                "active_connections": metric.active_connections,
                "query_count": metric.query_count,
                "error_count": metric.error_count,
                "response_time_avg": metric.response_time_avg
            })
        
        # 计算统计信息
        avg_cpu = sum(m.cpu_usage for m in metrics if m.cpu_usage) / len([m for m in metrics if m.cpu_usage])
        avg_memory = sum(m.memory_usage for m in metrics if m.memory_usage) / len([m for m in metrics if m.memory_usage])
        total_queries = sum(m.query_count for m in metrics if m.query_count)
        total_errors = sum(m.error_count for m in metrics if m.error_count)
        
        return {
            "time_range": {
                "start": start_time,
                "end": end_time,
                "hours": hours
            },
            "summary": {
                "avg_cpu_usage": round(avg_cpu, 2),
                "avg_memory_usage": round(avg_memory, 2),
                "total_queries": total_queries,
                "total_errors": total_errors,
                "error_rate": round((total_errors / max(total_queries, 1)) * 100, 2)
            },
            "metrics": formatted_metrics
        }
        
    except Exception as e:
        logger.error(f"获取系统指标失败: {e}")
        raise HTTPException(status_code=500, detail="获取系统指标失败")


@router.post("/system/cleanup", summary="系统清理")
async def system_cleanup(
    cleanup_logs: bool = False,
    cleanup_temp: bool = False,
    cleanup_old_queries: bool = False,
    days_to_keep: int = 30,
    db: Session = Depends(get_db)
):
    """
    执行系统清理操作
    """
    try:
        cleanup_results = {
            "logs_cleaned": False,
            "temp_files_cleaned": False,
            "old_queries_cleaned": False,
            "space_freed": 0,
            "details": []
        }
        
        # 清理日志文件
        if cleanup_logs:
            try:
                logs_dir = settings.LOG_DIR
                if os.path.exists(logs_dir):
                    log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
                    space_freed = 0
                    
                    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
                    
                    for log_file in log_files:
                        file_path = os.path.join(logs_dir, log_file)
                        file_stat = os.stat(file_path)
                        file_date = datetime.fromtimestamp(file_stat.st_mtime)
                        
                        if file_date < cutoff_date:
                            space_freed += file_stat.st_size
                            os.remove(file_path)
                    
                    cleanup_results["logs_cleaned"] = True
                    cleanup_results["space_freed"] += space_freed
                    cleanup_results["details"].append(
                        f"清理了 {len([f for f in log_files if datetime.fromtimestamp(os.stat(os.path.join(logs_dir, f)).st_mtime) < cutoff_date])} 个日志文件"
                    )
                    
            except Exception as e:
                cleanup_results["details"].append(f"清理日志文件失败: {e}")
        
        # 清理临时文件
        if cleanup_temp:
            try:
                temp_dirs = [
                    os.path.join(settings.DATA_DIR, "temp"),
                    os.path.join(settings.DATA_DIR, "cache")
                ]
                
                space_freed = 0
                files_cleaned = 0
                
                for temp_dir in temp_dirs:
                    if os.path.exists(temp_dir):
                        for root, dirs, files in os.walk(temp_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                try:
                                    space_freed += os.path.getsize(file_path)
                                    os.remove(file_path)
                                    files_cleaned += 1
                                except Exception:
                                    pass
                
                cleanup_results["temp_files_cleaned"] = True
                cleanup_results["space_freed"] += space_freed
                cleanup_results["details"].append(
                    f"清理了 {files_cleaned} 个临时文件"
                )
                
            except Exception as e:
                cleanup_results["details"].append(f"清理临时文件失败: {e}")
        
        # 清理旧查询记录
        if cleanup_old_queries:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
                
                old_queries = db.query(QueryHistory).filter(
                    QueryHistory.created_time < cutoff_date
                ).count()
                
                db.query(QueryHistory).filter(
                    QueryHistory.created_time < cutoff_date
                ).delete()
                
                db.commit()
                
                cleanup_results["old_queries_cleaned"] = True
                cleanup_results["details"].append(
                    f"清理了 {old_queries} 条旧查询记录"
                )
                
            except Exception as e:
                cleanup_results["details"].append(f"清理旧查询记录失败: {e}")
                db.rollback()
        
        logger.info(f"系统清理完成: {cleanup_results}")
        
        return cleanup_results
        
    except Exception as e:
        logger.error(f"系统清理失败: {e}")
        raise HTTPException(status_code=500, detail="系统清理失败")


@router.get("/documents/statistics", summary="获取文档统计")
async def get_document_statistics(db: Session = Depends(get_db)):
    """获取文档相关统计信息"""
    try:
        # 文档统计
        total_documents = db.query(Document).count()
        processed_documents = db.query(Document).filter(Document.is_processed == True).count()
        failed_documents = db.query(Document).filter(Document.processing_status == "failed").count()
        
        # 文档大小统计
        total_size = db.query(func.sum(Document.file_size)).scalar() or 0
        avg_size = db.query(func.avg(Document.file_size)).scalar() or 0
        
        # 文档块统计
        total_chunks = db.query(DocumentChunk).count()
        avg_chunks_per_doc = total_chunks / max(processed_documents, 1)
        
        # 按状态分组统计
        status_stats = db.query(
            Document.processing_status,
            func.count(Document.id)
        ).group_by(Document.processing_status).all()
        
        # 最近上传的文档
        recent_documents = db.query(Document).order_by(
            desc(Document.upload_time)
        ).limit(10).all()
        
        return {
            "summary": {
                "total_documents": total_documents,
                "processed_documents": processed_documents,
                "failed_documents": failed_documents,
                "processing_rate": round((processed_documents / max(total_documents, 1)) * 100, 2),
                "total_size_bytes": total_size,
                "average_size_bytes": round(avg_size, 2),
                "total_chunks": total_chunks,
                "average_chunks_per_document": round(avg_chunks_per_doc, 2)
            },
            "status_breakdown": {
                status: count for status, count in status_stats
            },
            "recent_documents": [
                {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "size": doc.file_size,
                    "status": doc.processing_status,
                    "upload_time": doc.upload_time
                }
                for doc in recent_documents
            ]
        }
        
    except Exception as e:
        logger.error(f"获取文档统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取文档统计失败")


@router.get("/queries/analytics", summary="获取查询分析")
async def get_query_analytics(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """获取查询分析数据"""
    try:
        # 计算时间范围
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # 基础统计
        total_queries = db.query(QueryHistory).filter(
            QueryHistory.created_time >= start_date
        ).count()
        
        avg_response_time = db.query(func.avg(QueryHistory.response_time)).filter(
            QueryHistory.created_time >= start_date
        ).scalar() or 0
        
        # 按查询类型统计
        type_stats = db.query(
            QueryHistory.model_used,
            func.count(QueryHistory.id),
            func.avg(QueryHistory.response_time)
        ).filter(
            QueryHistory.created_time >= start_date
        ).group_by(QueryHistory.model_used).all()
        
        # 用户满意度统计
        feedback_stats = db.query(
            QueryHistory.rating,
            func.count(QueryHistory.id)
        ).filter(
            QueryHistory.created_time >= start_date,
            QueryHistory.rating.isnot(None)
        ).group_by(QueryHistory.rating).all()
        
        avg_rating = db.query(func.avg(QueryHistory.rating)).filter(
            QueryHistory.created_time >= start_date,
            QueryHistory.rating.isnot(None)
        ).scalar() or 0
        
        # 每日查询量统计
        daily_stats = db.query(
            func.date(QueryHistory.created_time).label('date'),
            func.count(QueryHistory.id).label('count'),
            func.avg(QueryHistory.response_time).label('avg_time')
        ).filter(
            QueryHistory.created_time >= start_date
        ).group_by(func.date(QueryHistory.created_time)).all()
        
        # 最常见的查询
        common_queries = db.query(
            QueryHistory.query,
            func.count(QueryHistory.id).label('frequency')
        ).filter(
            QueryHistory.created_time >= start_date
        ).group_by(QueryHistory.query).order_by(
            desc('frequency')
        ).limit(10).all()
        
        return {
            "time_range": {
                "start_date": start_date,
                "end_date": end_date,
                "days": days
            },
            "summary": {
                "total_queries": total_queries,
                "average_response_time": round(avg_response_time, 3),
                "queries_per_day": round(total_queries / max(days, 1), 2),
                "average_rating": round(avg_rating, 2)
            },
            "query_types": [
                {
                    "type": qtype,
                    "count": count,
                    "avg_response_time": round(avg_time, 3)
                }
                for qtype, count, avg_time in type_stats
            ],
            "feedback_distribution": [
                {
                    "rating": rating,
                    "count": count
                }
                for rating, count in feedback_stats
            ],
            "daily_statistics": [
                {
                    "date": date,
                    "query_count": count,
                    "avg_response_time": round(avg_time, 3)
                }
                for date, count, avg_time in daily_stats
            ],
            "common_queries": [
                {
                    "question": question[:100] + "..." if len(question) > 100 else question,
                    "frequency": frequency
                }
                for question, frequency in common_queries
            ]
        }
        
    except Exception as e:
        logger.error(f"获取查询分析失败: {e}")
        raise HTTPException(status_code=500, detail="获取查询分析失败")


@router.post("/system/backup", summary="创建系统备份")
async def create_system_backup(
    include_documents: bool = True,
    include_database: bool = True,
    include_vector_db: bool = False,
    db: Session = Depends(get_db)
):
    """创建系统备份"""
    try:
        backup_dir = os.path.join(settings.DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
        backup_path = os.path.join(backup_dir, backup_name)
        os.makedirs(backup_path, exist_ok=True)
        
        backup_info = {
            "backup_name": backup_name,
            "backup_path": backup_path,
            "created_at": datetime.now(),
            "components": [],
            "total_size": 0
        }
        
        # 备份数据库
        if include_database:
            try:
                db_source = settings.DATABASE_URL.replace("sqlite:///", "")
                if os.path.exists(db_source):
                    db_backup = os.path.join(backup_path, "database.db")
                    shutil.copy2(db_source, db_backup)
                    size = os.path.getsize(db_backup)
                    backup_info["components"].append({
                        "name": "database",
                        "size": size,
                        "status": "success"
                    })
                    backup_info["total_size"] += size
            except Exception as e:
                backup_info["components"].append({
                    "name": "database",
                    "size": 0,
                    "status": "failed",
                    "error": str(e)
                })
        
        # 备份文档
        if include_documents:
            try:
                docs_source = os.path.join(settings.DATA_DIR, "documents")
                if os.path.exists(docs_source):
                    docs_backup = os.path.join(backup_path, "documents")
                    shutil.copytree(docs_source, docs_backup)
                    
                    # 计算大小
                    size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(docs_backup)
                        for filename in filenames
                    )
                    
                    backup_info["components"].append({
                        "name": "documents",
                        "size": size,
                        "status": "success"
                    })
                    backup_info["total_size"] += size
            except Exception as e:
                backup_info["components"].append({
                    "name": "documents",
                    "size": 0,
                    "status": "failed",
                    "error": str(e)
                })
        
        # 备份向量数据库
        if include_vector_db:
            try:
                vector_source = os.path.join(settings.DATA_DIR, "vector_db")
                if os.path.exists(vector_source):
                    vector_backup = os.path.join(backup_path, "vector_db")
                    shutil.copytree(vector_source, vector_backup)
                    
                    # 计算大小
                    size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(vector_backup)
                        for filename in filenames
                    )
                    
                    backup_info["components"].append({
                        "name": "vector_db",
                        "size": size,
                        "status": "success"
                    })
                    backup_info["total_size"] += size
            except Exception as e:
                backup_info["components"].append({
                    "name": "vector_db",
                    "size": 0,
                    "status": "failed",
                    "error": str(e)
                })
        
        # 创建备份信息文件
        import json
        info_file = os.path.join(backup_path, "backup_info.json")
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(backup_info, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"系统备份创建完成: {backup_name}")
        
        return backup_info
        
    except Exception as e:
        logger.error(f"创建系统备份失败: {e}")
        raise HTTPException(status_code=500, detail="创建系统备份失败")


@router.get("/system/backups", summary="获取备份列表")
async def get_backup_list():
    """获取系统备份列表"""
    try:
        backup_dir = os.path.join(settings.DATA_DIR, "backups")
        
        if not os.path.exists(backup_dir):
            return {"backups": []}
        
        backups = []
        for item in os.listdir(backup_dir):
            item_path = os.path.join(backup_dir, item)
            if os.path.isdir(item_path):
                info_file = os.path.join(item_path, "backup_info.json")
                if os.path.exists(info_file):
                    try:
                        import json
                        with open(info_file, 'r', encoding='utf-8') as f:
                            backup_info = json.load(f)
                        backups.append(backup_info)
                    except Exception:
                        # 如果无法读取备份信息,创建基本信息
                        stat = os.stat(item_path)
                        backups.append({
                            "backup_name": item,
                            "backup_path": item_path,
                            "created_at": datetime.fromtimestamp(stat.st_ctime),
                            "total_size": sum(
                                os.path.getsize(os.path.join(dirpath, filename))
                                for dirpath, dirnames, filenames in os.walk(item_path)
                                for filename in filenames
                            )
                        })
        
        # 按创建时间排序
        backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return {"backups": backups}
        
    except Exception as e:
        logger.error(f"获取备份列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取备份列表失败")


@router.delete("/system/backups/{backup_name}", summary="删除备份")
async def delete_backup(backup_name: str):
    """删除指定的系统备份"""
    try:
        backup_dir = os.path.join(settings.DATA_DIR, "backups")
        backup_path = os.path.join(backup_dir, backup_name)
        
        if not os.path.exists(backup_path):
            raise HTTPException(status_code=404, detail="备份不存在")
        
        if not os.path.isdir(backup_path):
            raise HTTPException(status_code=400, detail="无效的备份路径")
        
        # 安全检查:确保路径在备份目录内
        if not os.path.abspath(backup_path).startswith(os.path.abspath(backup_dir)):
            raise HTTPException(status_code=400, detail="无效的备份路径")
        
        shutil.rmtree(backup_path)
        
        logger.info(f"备份删除成功: {backup_name}")
        
        return {"message": "备份删除成功", "backup_name": backup_name}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除备份失败: {e}")
        raise HTTPException(status_code=500, detail="删除备份失败")


