from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app


def register_and_create_kb(client: TestClient) -> tuple[dict[str, str], int]:
    response = client.post(
        "/api/auth/register",
        json={"email": f"{uuid4().hex}@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    knowledge_base = client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": "Security test", "description": ""},
    )
    return headers, knowledge_base.json()["id"]


def test_auth_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit", 1)
    with TestClient(app) as client:
        first = client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "password123"},
        )
        second = client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "password123"},
        )
    assert first.status_code == 401
    assert second.status_code == 429
    assert second.headers["retry-after"] == str(settings.auth_rate_window_seconds)


def test_upload_size_and_pdf_signature_are_rejected(monkeypatch):
    with TestClient(app) as client:
        headers, knowledge_base_id = register_and_create_kb(client)
        monkeypatch.setattr(settings, "upload_max_bytes", 5)
        too_large = client.post(
            f"/api/documents/upload?knowledge_base_id={knowledge_base_id}",
            headers=headers,
            files={"file": ("large.txt", b"123456", "text/plain")},
        )
        monkeypatch.setattr(settings, "upload_max_bytes", 1024)
        invalid_pdf = client.post(
            f"/api/documents/upload?knowledge_base_id={knowledge_base_id}",
            headers=headers,
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        invalid_docx = client.post(
            f"/api/documents/upload?knowledge_base_id={knowledge_base_id}",
            headers=headers,
            files={"file": ("fake.docx", b"not a docx", "application/octet-stream")},
        )
        invalid_image = client.post(
            f"/api/documents/upload?knowledge_base_id={knowledge_base_id}",
            headers=headers,
            files={"file": ("fake.png", b"not an image", "image/png")},
        )
    assert too_large.status_code == 413
    assert invalid_pdf.status_code == 400
    assert invalid_docx.status_code == 400
    assert invalid_image.status_code == 400


def test_audit_log_contains_metadata_without_secrets():
    password = "password123"
    with TestClient(app) as client:
        headers, _ = register_and_create_kb(client)
        logs = client.get("/api/audit-logs", headers=headers)
    assert logs.status_code == 200
    body = logs.text
    assert "auth.register" in body
    assert "knowledge_base.create" in body
    assert password not in body
    assert "password_hash" not in body


def test_settings_load_secrets_from_files(tmp_path: Path):
    secret_file = tmp_path / "secret_key"
    llm_file = tmp_path / "llm_api_key"
    database_file = tmp_path / "database_url"
    secret_file.write_text("jwt-from-file\n", encoding="utf-8")
    llm_file.write_text("llm-from-file\n", encoding="utf-8")
    database_file.write_text("sqlite:///from-file.db\n", encoding="utf-8")

    loaded = Settings(
        _env_file=None,
        secret_key="fallback",
        llm_api_key="fallback",
        secret_key_file=secret_file,
        llm_api_key_file=llm_file,
        database_url_file=database_file,
    )
    assert loaded.secret_key == "jwt-from-file"
    assert loaded.llm_api_key == "llm-from-file"
    assert loaded.database_url == "sqlite:///from-file.db"


def test_knowledge_base_delete_requires_exact_name():
    with TestClient(app) as client:
        headers, knowledge_base_id = register_and_create_kb(client)
        rejected = client.delete(
            f"/api/knowledge-bases/{knowledge_base_id}?confirmation=wrong",
            headers=headers,
        )
        deleted = client.delete(
            f"/api/knowledge-bases/{knowledge_base_id}?confirmation=Security%20test",
            headers=headers,
        )

    assert rejected.status_code == 409
    assert deleted.status_code == 204
