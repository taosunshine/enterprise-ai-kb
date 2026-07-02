from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "enterprise_ai_kb",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.celery_tasks"],
)
celery_app.conf.beat_schedule = {
    "purge-expired-recycle-bin-items-daily": {
        "task": "app.purge_expired_recycle_bin_items",
        "schedule": crontab(hour=2, minute=0),
    }
}
celery_app.conf.timezone = "UTC"
