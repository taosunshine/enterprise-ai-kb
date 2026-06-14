from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(backend_dir / "alembic.ini")
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")
