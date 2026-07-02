from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import Document, KnowledgeBase, User, utcnow
from app.schemas import RecycleBinItem
from app.services.audit import record_audit
from app.services.recycle_bin import (
    purge_document,
    purge_knowledge_base,
    remaining_days,
    restore_document,
    restore_knowledge_base,
    retention_expired,
)

router = APIRouter(tags=["recycle-bin"])
ITEM_MODELS = {"knowledge-base": KnowledgeBase, "document": Document}


def owned_deleted_item(db: Session, user_id: int, item_type: str, item_id: int):
    model = ITEM_MODELS.get(item_type)
    if model is None:
        raise HTTPException(status_code=404, detail="Recycle bin item not found")
    statement = select(model).where(model.id == item_id, model.deleted_at.is_not(None))
    if model is KnowledgeBase:
        statement = statement.where(KnowledgeBase.user_id == user_id)
    else:
        statement = statement.join(
            KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id
        ).where(KnowledgeBase.user_id == user_id)
    item = db.scalar(statement.execution_options(include_deleted=True))
    if not item or retention_expired(item.purge_after):
        raise HTTPException(status_code=404, detail="Recycle bin item not found")
    return model, item


@router.get("/recycle-bin", response_model=list[RecycleBinItem])
@router.get("/trash", response_model=list[RecycleBinItem])
def list_recycle_bin(
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    knowledge_bases = db.scalars(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.user_id == user.id,
            KnowledgeBase.deleted_at.is_not(None),
            KnowledgeBase.purge_after > utcnow(),
        )
        .execution_options(include_deleted=True)
    ).all()
    documents = db.scalars(
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            KnowledgeBase.user_id == user.id,
            Document.deleted_at.is_not(None),
            Document.purge_after > utcnow(),
            KnowledgeBase.deleted_at.is_(None),
        )
        .execution_options(include_deleted=True)
    ).all()
    items = [
        RecycleBinItem(
            item_type="knowledge-base",
            item_id=item.id,
            name=item.name,
            deleted_at=item.deleted_at,
            purge_after=item.purge_after,
            remaining_days=remaining_days(item.purge_after),
        )
        for item in knowledge_bases
    ] + [
        RecycleBinItem(
            item_type="document",
            item_id=item.id,
            name=item.filename,
            deleted_at=item.deleted_at,
            purge_after=item.purge_after,
            remaining_days=remaining_days(item.purge_after),
        )
        for item in documents
    ]
    return sorted(items, key=lambda item: item.deleted_at, reverse=True)[:limit]


@router.post("/recycle-bin/{item_type}/{item_id}/restore", status_code=204)
@router.post("/trash/{item_type}/{item_id}/restore", status_code=204)
def restore_recycle_bin_item(
    item_type: str,
    item_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, _ = owned_deleted_item(db, user.id, item_type, item_id)
    if model is KnowledgeBase:
        restore_knowledge_base(db, item_id)
    else:
        restore_document(db, item_id)
    db.commit()
    record_audit(
        db,
        request,
        action="recycle_bin.restore",
        user_id=user.id,
        resource_type=item_type,
        resource_id=item_id,
    )


@router.delete("/recycle-bin/{item_type}/{item_id}", status_code=204)
@router.delete("/trash/{item_type}/{item_id}", status_code=204)
def purge_recycle_bin_item(
    item_type: str,
    item_id: int,
    confirmation: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, item = owned_deleted_item(db, user.id, item_type, item_id)
    expected_name = item.name if model is KnowledgeBase else item.filename
    if confirmation != expected_name:
        raise HTTPException(status_code=409, detail="Recycle bin item confirmation does not match")
    if model is KnowledgeBase:
        purge_knowledge_base(db, item)
    else:
        purge_document(db, item)
    db.commit()
    record_audit(
        db,
        request,
        action="recycle_bin.permanent_delete",
        user_id=user.id,
        resource_type=item_type,
        resource_id=item_id,
    )
