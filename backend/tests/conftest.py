import pytest
from sqlalchemy import delete, inspect

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models import RateLimitEvent


@pytest.fixture(autouse=True)
def eager_processing_tasks(monkeypatch):
    monkeypatch.setattr(settings, "task_eager", True)
    if inspect(engine).has_table("rate_limit_events"):
        with SessionLocal() as db:
            db.execute(delete(RateLimitEvent))
            db.commit()
