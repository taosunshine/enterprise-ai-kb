from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models import Document, ProcessingTask, utcnow
from app.services.tasks import claim_task, recover_stale_tasks, run_task


def upload_document(client: TestClient, monkeypatch) -> tuple[int, int]:
    monkeypatch.setattr(settings, "task_eager", False)
    registered = client.post(
        "/api/auth/register",
        json={"email": f"{uuid4().hex}@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    knowledge_base = client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": "Tasks", "description": ""},
    ).json()
    document = client.post(
        f"/api/documents/upload?knowledge_base_id={knowledge_base['id']}",
        headers=headers,
        files={"file": ("task.txt", "用于测试持久任务队列。", "text/plain")},
    ).json()
    with SessionLocal() as db:
        task = db.scalar(
            select(ProcessingTask).where(ProcessingTask.document_id == document["id"])
        )
        return document["id"], task.id


def test_failed_task_retries_then_marks_document_failed(monkeypatch):
    with TestClient(app) as client:
        document_id, task_id = upload_document(client, monkeypatch)
        monkeypatch.setattr(settings, "task_retry_base_seconds", 0)
        monkeypatch.setattr(
            "app.services.tasks.process_document",
            lambda *_: (_ for _ in ()).throw(RuntimeError("parser unavailable")),
        )
        with SessionLocal() as db:
            task = db.get(ProcessingTask, task_id)
            task.max_attempts = 2
            db.commit()

        with SessionLocal() as db:
            first = claim_task(db, task_id)
        run_task(first.id)
        with SessionLocal() as db:
            assert db.get(ProcessingTask, task_id).status == "retry"
            assert db.get(Document, document_id).status == "queued"

        with SessionLocal() as db:
            second = claim_task(db, task_id)
        run_task(second.id)
        with SessionLocal() as db:
            assert db.get(ProcessingTask, task_id).status == "failed"
            assert db.get(Document, document_id).status == "failed"


def test_stale_running_task_is_recovered(monkeypatch):
    with TestClient(app) as client:
        document_id, task_id = upload_document(client, monkeypatch)
        with SessionLocal() as db:
            task = db.get(ProcessingTask, task_id)
            task.status = "running"
            task.locked_at = utcnow() - timedelta(hours=1)
            document = db.get(Document, document_id)
            document.status = "processing"
            db.commit()

        with SessionLocal() as db:
            assert recover_stale_tasks(db) == 1
            assert db.get(ProcessingTask, task_id).status == "retry"
            assert db.get(Document, document_id).status == "queued"
