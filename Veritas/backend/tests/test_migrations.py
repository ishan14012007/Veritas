import os
import tempfile
import pytest
from alembic import command
from alembic.config import Config


def test_alembic_migrations_upgrade_and_downgrade():
    """Verify that a fresh database can be created entirely through migrations,
    and cleanly rolled back via downgrade.
    """
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_path = temp_db.name
        sqlite_url = f"sqlite+aiosqlite:///{db_path}"

        # Setup alembic configuration pointing to backend/alembic.ini
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        # 2. Downgrade to base
        command.downgrade(alembic_cfg, "base")

        # 3. Upgrade to head again to ensure repeatability
        command.upgrade(alembic_cfg, "head")

