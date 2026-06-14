from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import KnowledgeBase, User
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user.id)).all()


@router.post("", response_model=KnowledgeBaseRead, status_code=201)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = KnowledgeBase(user_id=user.id, name=payload.name, description=payload.description)
    db.add(item)
    db.commit()
    db.refresh(item)
    record_audit(
        db, request, action="knowledge_base.create", user_id=user.id,
        resource_type="knowledge_base", resource_id=item.id
    )
    return item


@router.put("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user.id
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    item.name = payload.name
    item.description = payload.description
    db.commit()
    db.refresh(item)
    record_audit(
        db, request, action="knowledge_base.update", user_id=user.id,
        resource_type="knowledge_base", resource_id=item.id
    )
    return item


@router.delete("/{knowledge_base_id}", status_code=204)
def delete_knowledge_base(
    knowledge_base_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user.id
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    document_paths = [Path(document.file_path) for document in item.documents]
    db.delete(item)
    db.commit()
    for path in document_paths:
        path.unlink(missing_ok=True)
    record_audit(
        db, request, action="knowledge_base.delete", user_id=user.id,
        resource_type="knowledge_base", resource_id=knowledge_base_id
    )
