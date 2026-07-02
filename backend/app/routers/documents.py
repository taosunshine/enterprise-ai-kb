from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import Document, KnowledgeBase, User
from app.schemas import DocumentRead
from app.services.audit import record_audit
from app.services.rate_limits import enforce_rate_limit
from app.services.recycle_bin import soft_delete_document
from app.services.tasks import enqueue_document_task

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".md",
    ".txt",
    ".csv",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


@router.get("", response_model=list[DocumentRead])
def list_documents(
    knowledge_base_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge_base = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user.id
        )
    )
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return db.scalars(select(Document).where(Document.knowledge_base_id == knowledge_base_id)).all()


@router.post("/upload", response_model=DocumentRead, status_code=202)
def upload_document(
    knowledge_base_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge_base = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user.id
        )
    )
    suffix = Path(file.filename or "").suffix.lower()
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX, Markdown, TXT, CSV, HTML and images are supported",
        )
    document_count = db.scalar(
        select(func.count(Document.id)).where(Document.knowledge_base_id == knowledge_base_id)
    )
    if document_count is not None and document_count >= settings.upload_max_documents_per_kb:
        raise HTTPException(status_code=409, detail="Knowledge base document limit reached")
    enforce_rate_limit(
        db,
        key=str(user.id),
        scope="document_upload",
        limit=settings.upload_rate_limit,
        window_seconds=settings.upload_rate_window_seconds,
    )

    target_dir = settings.upload_dir / str(user.id) / str(knowledge_base_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex}{suffix}"
    size = 0
    first_bytes = b""
    try:
        with target_path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                if not first_bytes:
                    first_bytes = chunk[:1024]
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded file is too large")
                output.write(chunk)
        if suffix == ".pdf" and not first_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file")
        if suffix == ".docx" and not first_bytes.startswith(b"PK"):
            raise HTTPException(status_code=400, detail="Invalid DOCX file")
        image_headers = {
            ".png": b"\x89PNG\r\n\x1a\n",
            ".jpg": b"\xff\xd8\xff",
            ".jpeg": b"\xff\xd8\xff",
            ".webp": b"RIFF",
        }
        if suffix in image_headers and not first_bytes.startswith(image_headers[suffix]):
            raise HTTPException(status_code=400, detail="Invalid image file")
        if suffix in {".md", ".txt", ".csv", ".html", ".htm"} and b"\x00" in first_bytes:
            raise HTTPException(status_code=400, detail="Invalid text file")
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    document = Document(
        knowledge_base_id=knowledge_base_id,
        filename=Path(file.filename or target_path.name).name,
        file_path=str(target_path),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    enqueue_document_task(db, document)
    record_audit(
        db,
        request,
        action="document.upload",
        user_id=user.id,
        resource_type="document",
        resource_id=document.id,
        details={"filename": document.filename, "size_bytes": size},
    )
    return document


def owned_document(db: Session, user_id: int, document_id: int) -> Document:
    document = db.scalar(
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(Document.id == document_id, KnowledgeBase.user_id == user_id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/{document_id}/reprocess", response_model=DocumentRead, status_code=202)
def reprocess_document(
    document_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = owned_document(db, user.id, document_id)
    enqueue_document_task(db, document)
    record_audit(
        db,
        request,
        action="document.reprocess",
        user_id=user.id,
        resource_type="document",
        resource_id=document.id,
    )
    return document


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = owned_document(db, user.id, document_id)
    soft_delete_document(db, document, user.id)
    db.commit()
    record_audit(
        db,
        request,
        action="document.delete",
        user_id=user.id,
        resource_type="document",
        resource_id=document_id,
    )
