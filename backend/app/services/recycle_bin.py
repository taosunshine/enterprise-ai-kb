import math
from datetime import UTC, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ChatMessage,
    ChatSession,
    ChunkEmbedding,
    Document,
    DocumentChunk,
    KnowledgeBase,
    ProcessingTask,
    utcnow,
)
from app.services.audit import add_system_audit

SOFT_DELETE_MODELS = (KnowledgeBase, Document, DocumentChunk, ChunkEmbedding)


def deletion_values(user_id: int) -> dict:
    deleted_at = utcnow()
    return {
        "deleted_at": deleted_at,
        "purge_after": deleted_at + timedelta(days=settings.recycle_bin_retention_days),
        "deleted_by_user_id": user_id,
    }


def soft_delete_document(db: Session, document: Document, user_id: int) -> None:
    values = deletion_values(user_id)
    db.execute(update(Document).where(Document.id == document.id).values(**values))
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)
    db.execute(update(DocumentChunk).where(DocumentChunk.document_id == document.id).values(**values))
    db.execute(update(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids)).values(**values))


def soft_delete_knowledge_base(db: Session, knowledge_base: KnowledgeBase, user_id: int) -> None:
    values = deletion_values(user_id)
    document_ids = select(Document.id).where(Document.knowledge_base_id == knowledge_base.id)
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id.in_(document_ids))
    db.execute(update(KnowledgeBase).where(KnowledgeBase.id == knowledge_base.id).values(**values))
    db.execute(update(Document).where(Document.knowledge_base_id == knowledge_base.id).values(**values))
    db.execute(update(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids)).values(**values))
    db.execute(update(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids)).values(**values))


def restore_document(db: Session, document_id: int) -> None:
    values = {"deleted_at": None, "purge_after": None, "deleted_by_user_id": None}
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
    db.execute(update(Document).where(Document.id == document_id).values(**values))
    db.execute(update(DocumentChunk).where(DocumentChunk.document_id == document_id).values(**values))
    db.execute(update(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids)).values(**values))


def restore_knowledge_base(db: Session, knowledge_base_id: int) -> None:
    values = {"deleted_at": None, "purge_after": None, "deleted_by_user_id": None}
    document_ids = select(Document.id).where(Document.knowledge_base_id == knowledge_base_id)
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id.in_(document_ids))
    db.execute(update(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id).values(**values))
    db.execute(update(Document).where(Document.knowledge_base_id == knowledge_base_id).values(**values))
    db.execute(update(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids)).values(**values))
    db.execute(update(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids)).values(**values))


def remaining_days(purge_after) -> int:
    if purge_after.tzinfo is None:
        purge_after = purge_after.replace(tzinfo=UTC)
    return max(0, math.ceil((purge_after - utcnow()).total_seconds() / 86400))


def retention_expired(purge_after) -> bool:
    if purge_after is None:
        return True
    if purge_after.tzinfo is None:
        purge_after = purge_after.replace(tzinfo=UTC)
    return purge_after <= utcnow()


def purge_document(db: Session, document: Document) -> None:
    Path(document.file_path).unlink(missing_ok=True)
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)
    db.execute(delete(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids)))
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.execute(delete(ProcessingTask).where(ProcessingTask.document_id == document.id))
    db.execute(delete(Document).where(Document.id == document.id))


def purge_knowledge_base(db: Session, knowledge_base: KnowledgeBase) -> None:
    documents = db.scalars(
        select(Document)
        .where(Document.knowledge_base_id == knowledge_base.id)
        .execution_options(include_deleted=True)
    ).all()
    for document in documents:
        purge_document(db, document)
    session_ids = select(ChatSession.id).where(ChatSession.knowledge_base_id == knowledge_base.id)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
    db.execute(delete(ChatSession).where(ChatSession.knowledge_base_id == knowledge_base.id))
    db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == knowledge_base.id))


def purge_expired_items(db: Session) -> dict[str, int]:
    cutoff = utcnow()
    knowledge_bases = db.scalars(
        select(KnowledgeBase)
        .where(KnowledgeBase.purge_after <= cutoff)
        .execution_options(include_deleted=True)
    ).all()
    knowledge_base_ids = {item.id for item in knowledge_bases}
    documents = db.scalars(
        select(Document)
        .where(Document.purge_after <= cutoff, Document.knowledge_base_id.not_in(knowledge_base_ids))
        .execution_options(include_deleted=True)
    ).all()
    for document in documents:
        add_system_audit(
            db,
            action="recycle_bin.purge",
            user_id=document.deleted_by_user_id,
            resource_type="document",
            resource_id=document.id,
        )
        purge_document(db, document)
    for knowledge_base in knowledge_bases:
        add_system_audit(
            db,
            action="recycle_bin.purge",
            user_id=knowledge_base.deleted_by_user_id,
            resource_type="knowledge_base",
            resource_id=knowledge_base.id,
        )
        purge_knowledge_base(db, knowledge_base)
    db.commit()
    return {"knowledge_bases": len(knowledge_bases), "documents": len(documents)}
