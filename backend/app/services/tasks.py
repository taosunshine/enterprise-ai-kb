import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Document, ProcessingTask
from app.services.documents import process_document

logger = logging.getLogger("app.tasks")
ACTIVE_STATUSES = ("pending", "retry", "running")


def now() -> datetime:
    return datetime.now(UTC)


def enqueue_document_task(db: Session, document: Document) -> ProcessingTask:
    active = db.scalar(
        select(ProcessingTask).where(
            ProcessingTask.document_id == document.id,
            ProcessingTask.status.in_(ACTIVE_STATUSES),
        )
    )
    if active:
        return active
    document.status = "queued"
    document.error_message = ""
    task = ProcessingTask(document_id=document.id, max_attempts=settings.task_max_attempts)
    db.add(task)
    db.commit()
    db.refresh(task)
    if settings.task_eager:
        with SessionLocal() as eager_db:
            claimed = claim_task(eager_db, task.id)
        if claimed:
            run_task(claimed.id)
        db.refresh(document)
    return task


def recover_stale_tasks(db: Session) -> int:
    cutoff = now() - timedelta(seconds=settings.task_stale_after_seconds)
    tasks = db.scalars(
        select(ProcessingTask).where(
            ProcessingTask.status == "running",
            ProcessingTask.locked_at < cutoff,
        )
    ).all()
    for task in tasks:
        task.status = "retry"
        task.available_at = now()
        task.locked_at = None
        task.last_error = "Recovered after worker interruption"
        document = db.get(Document, task.document_id)
        if document:
            document.status = "queued"
            document.error_message = ""
    db.commit()
    return len(tasks)


def claim_query():
    return select(ProcessingTask).where(
        ProcessingTask.status.in_(("pending", "retry")),
        ProcessingTask.available_at <= now(),
    )


def claim_task(db: Session, task_id: int) -> ProcessingTask | None:
    query = claim_query().where(ProcessingTask.id == task_id)
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    task = db.scalar(query)
    if not task:
        return None
    task.status = "running"
    task.attempts += 1
    task.locked_at = now()
    task.updated_at = now()
    db.commit()
    db.refresh(task)
    return task


def claim_next_task(db: Session) -> ProcessingTask | None:
    query = claim_query().order_by(ProcessingTask.created_at, ProcessingTask.id).limit(1)
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    task = db.scalar(query)
    if not task:
        return None
    task.status = "running"
    task.attempts += 1
    task.locked_at = now()
    task.updated_at = now()
    db.commit()
    db.refresh(task)
    return task


def run_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(ProcessingTask, task_id)
        if not task:
            return
        try:
            process_document(task.document_id, db)
            task = db.get(ProcessingTask, task_id)
            task.status = "completed"
            task.locked_at = None
            task.last_error = ""
            task.updated_at = now()
            db.commit()
            logger.info("processing_task_completed task=%s document=%s", task.id, task.document_id)
        except Exception as exc:
            db.rollback()
            task = db.get(ProcessingTask, task_id)
            document = db.get(Document, task.document_id) if task else None
            if not task:
                return
            task.last_error = str(exc)[:1000]
            task.locked_at = None
            task.updated_at = now()
            if task.attempts < task.max_attempts:
                delay = settings.task_retry_base_seconds * (2 ** (task.attempts - 1))
                task.status = "retry"
                task.available_at = now() + timedelta(seconds=delay)
                if document:
                    document.status = "queued"
                    document.error_message = f"Retrying after error: {task.last_error}"
            else:
                task.status = "failed"
                if document:
                    document.status = "failed"
                    document.error_message = task.last_error
            db.commit()
            logger.exception("processing_task_failed task=%s attempt=%s", task.id, task.attempts)


def run_next_task() -> bool:
    with SessionLocal() as db:
        task = claim_next_task(db)
    if not task:
        return False
    run_task(task.id)
    return True


def reset_all_running_tasks() -> int:
    with SessionLocal() as db:
        result = db.execute(
            update(ProcessingTask)
            .where(ProcessingTask.status == "running")
            .values(status="retry", available_at=now(), locked_at=None)
        )
        db.commit()
        return result.rowcount
