import logging

from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.recycle_bin import purge_expired_items

logger = logging.getLogger("app.celery_tasks")


@celery_app.task(name="app.purge_expired_recycle_bin_items")
def purge_expired_recycle_bin_items() -> dict[str, int]:
    with SessionLocal() as db:
        result = purge_expired_items(db)
    logger.info("recycle_bin_purge_completed result=%s", result)
    return result
