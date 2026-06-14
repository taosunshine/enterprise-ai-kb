import logging
import time

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.migrations import upgrade_database
from app.services.tasks import recover_stale_tasks, run_next_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.worker")


def main() -> None:
    upgrade_database()
    with SessionLocal() as db:
        recovered = recover_stale_tasks(db)
    logger.info("worker_started recovered_tasks=%s", recovered)
    while True:
        if not run_next_task():
            time.sleep(settings.task_poll_interval_seconds)


if __name__ == "__main__":
    main()
