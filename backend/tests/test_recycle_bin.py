from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.main import app
from app.models import ChunkEmbedding, Document, DocumentChunk, utcnow
from app.services.recycle_bin import purge_expired_items


def create_document(client: TestClient) -> tuple[dict[str, str], int, int]:
    registered = client.post(
        "/api/auth/register",
        json={"email": f"{uuid4().hex}@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    knowledge_base = client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": "Recycle test", "description": ""},
    ).json()
    document = client.post(
        f"/api/documents/upload?knowledge_base_id={knowledge_base['id']}",
        headers=headers,
        files={"file": ("recycle.txt", "recycle bin searchable content", "text/plain")},
    ).json()
    return headers, knowledge_base["id"], document["id"]


def test_document_soft_delete_is_hidden_and_can_be_restored():
    with TestClient(app) as client:
        headers, knowledge_base_id, document_id = create_document(client)
        deleted = client.delete(f"/api/documents/{document_id}", headers=headers)
        assert deleted.status_code == 204
        assert client.get(
            f"/api/documents?knowledge_base_id={knowledge_base_id}", headers=headers
        ).json() == []

        recycle_bin = client.get("/api/recycle-bin", headers=headers).json()
        assert recycle_bin[0]["item_type"] == "document"
        assert recycle_bin[0]["item_id"] == document_id
        assert 29 <= recycle_bin[0]["remaining_days"] <= 30

        with SessionLocal() as db:
            document = db.scalar(
                select(Document)
                .where(Document.id == document_id)
                .execution_options(include_deleted=True)
            )
            chunk = db.scalar(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .execution_options(include_deleted=True)
            )
            embedding = db.scalar(
                select(ChunkEmbedding)
                .where(ChunkEmbedding.chunk_id == chunk.id)
                .execution_options(include_deleted=True)
            )
            assert document.deleted_at and chunk.deleted_at and embedding.deleted_at

        restored = client.post(
            f"/api/recycle-bin/document/{document_id}/restore", headers=headers
        )
        assert restored.status_code == 204
        assert client.get(
            f"/api/documents?knowledge_base_id={knowledge_base_id}", headers=headers
        ).json()[0]["id"] == document_id

        with SessionLocal() as db:
            chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document_id))
            embedding = db.scalar(
                select(ChunkEmbedding).where(ChunkEmbedding.chunk_id == chunk.id)
            )
            assert chunk.deleted_at is None
            assert embedding.deleted_at is None


def test_knowledge_base_restore_restores_documents_chunks_and_vectors():
    with TestClient(app) as client:
        headers, knowledge_base_id, document_id = create_document(client)
        deleted = client.delete(
            f"/api/knowledge-bases/{knowledge_base_id}?confirmation=Recycle%20test",
            headers=headers,
        )
        assert deleted.status_code == 204
        assert client.get("/api/knowledge-bases", headers=headers).json() == []
        assert client.get("/api/recycle-bin", headers=headers).json()[0]["item_type"] == "knowledge-base"

        restored = client.post(
            f"/api/recycle-bin/knowledge-base/{knowledge_base_id}/restore", headers=headers
        )
        assert restored.status_code == 204
        assert client.get("/api/knowledge-bases", headers=headers).json()[0]["id"] == knowledge_base_id
        assert client.get(
            f"/api/documents?knowledge_base_id={knowledge_base_id}", headers=headers
        ).json()[0]["id"] == document_id


def test_expired_items_are_physically_purged_with_files_and_audit_log():
    with TestClient(app) as client:
        headers, knowledge_base_id, document_id = create_document(client)
        client.delete(f"/api/documents/{document_id}", headers=headers)

        with SessionLocal() as db:
            document = db.scalar(
                select(Document)
                .where(Document.id == document_id)
                .execution_options(include_deleted=True)
            )
            file_path = Path(document.file_path)
            document.purge_after = utcnow() - timedelta(days=1)
            db.commit()
            result = purge_expired_items(db)
            assert result == {"knowledge_bases": 0, "documents": 1}
            assert db.scalar(
                select(Document)
                .where(Document.id == document_id)
                .execution_options(include_deleted=True)
            ) is None
            assert not file_path.exists()

        logs = client.get("/api/audit-logs", headers=headers).json()
        assert any(log["action"] == "recycle_bin.purge" for log in logs)


def test_trash_alias_and_permanent_delete_requires_exact_confirmation():
    with TestClient(app) as client:
        headers, knowledge_base_id, document_id = create_document(client)
        client.delete(f"/api/documents/{document_id}", headers=headers)

        trash = client.get("/api/trash", headers=headers)
        assert trash.status_code == 200
        assert trash.json()[0]["item_id"] == document_id

        rejected = client.delete(
            f"/api/trash/document/{document_id}?confirmation=wrong",
            headers=headers,
        )
        assert rejected.status_code == 409
        assert client.get("/api/trash", headers=headers).json()[0]["item_id"] == document_id

        purged = client.delete(
            f"/api/trash/document/{document_id}?confirmation=recycle.txt",
            headers=headers,
        )
        assert purged.status_code == 204
        assert client.get("/api/trash", headers=headers).json() == []
        assert client.get(
            f"/api/documents?knowledge_base_id={knowledge_base_id}", headers=headers
        ).json() == []

        with SessionLocal() as db:
            assert db.scalar(
                select(Document)
                .where(Document.id == document_id)
                .execution_options(include_deleted=True)
            ) is None

        logs = client.get("/api/audit-logs", headers=headers).json()
        assert any(log["action"] == "recycle_bin.permanent_delete" for log in logs)
