"""SQLAlchemy ORM models aligned with existing service/API usage."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class QueryHistory(Base):
    """Persisted Q&A turns."""

    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    model_used = Column(String(128), nullable=True)  # reused as query_type
    response_time = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost = Column(Float, nullable=True)
    rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    session_id = Column(String(128), nullable=True, index=True)
    rewritten_query = Column(Text, nullable=True)
    rewriting_metadata_json = Column(Text, nullable=True)
    retrieved_chunks = Column(Text, nullable=True)
    created_time = Column(DateTime, default=datetime.utcnow, index=True)


class Document(Base):
    """Indexed insurance document (clause PDF)."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(512), nullable=False)
    original_name = Column(String(512), nullable=True)
    file_path = Column(String(1024), nullable=True)
    file_hash = Column(String(128), nullable=True, index=True)
    file_size = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    document_type = Column(String(128), nullable=True)
    product_name = Column(String(256), nullable=True)
    status = Column(String(64), default="active")
    created_time = Column(DateTime, default=datetime.utcnow)
    updated_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """Text chunk belonging to a document (SQLite side; vectors live in Chroma)."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    content_hash = Column(String(128), nullable=True)
    vector_id = Column(String(128), nullable=True)
    created_time = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")


class DocumentMetadata(Base):
    """Structured metadata rows written by ingest."""

    __tablename__ = "document_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(128), nullable=False, unique=True, index=True)
    product_name = Column(String(256), nullable=True, index=True)
    effective_date = Column(String(64), nullable=True)
    document_type = Column(String(128), nullable=True)
    status = Column(String(64), nullable=True, default="active")
    created_time = Column(DateTime, default=datetime.utcnow)


class GraphEntity(Base):
    """Knowledge-graph entity (optional advanced path)."""

    __tablename__ = "graph_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, index=True)
    entity_type = Column(String(128), nullable=False, index=True)
    created_time = Column(DateTime, default=datetime.utcnow)


class GraphRelation(Base):
    """Knowledge-graph edge (optional advanced path)."""

    __tablename__ = "graph_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entity_id = Column(Integer, ForeignKey("graph_entities.id"), nullable=False, index=True)
    target_entity_id = Column(Integer, ForeignKey("graph_entities.id"), nullable=False, index=True)
    relation_type = Column(String(128), nullable=False)
    chunk_id = Column(String(128), nullable=True, index=True)
    created_time = Column(DateTime, default=datetime.utcnow)


class SystemMetrics(Base):
    """Optional ops metrics rows for admin endpoints."""

    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    disk_usage = Column(Float, nullable=True)
    active_connections = Column(Integer, nullable=True)
    query_count = Column(Integer, nullable=True)
    error_count = Column(Integer, nullable=True)
    response_time_avg = Column(Float, nullable=True)
