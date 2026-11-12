import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Global engine and sessionmaker instances
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Initialize or return the cached async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        import os
        import socket
        settings = get_settings()
        db_url = settings.DATABASE_URL

        # If PostgreSQL on localhost is specified, check if it is reachable.
        # If not reachable (e.g. running on Render without local Postgres),
        # fall back to the pre-seeded SQLite database so ACCORD is 100% operational.
        if "postgresql" in db_url and "localhost" in db_url:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            try:
                port = 5432
                if ":" in db_url.split("@")[-1]:
                    try:
                        port = int(db_url.split("@")[-1].split(":")[1].split("/")[0])
                    except Exception:
                        pass
                res = sock.connect_ex(('127.0.0.1', port))
                if res != 0:
                    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                    sqlite_path = os.path.join(workspace_root, "Veritas", "veritas.db")
                    if not os.path.exists(sqlite_path):
                        sqlite_path = os.path.join(workspace_root, "veritas.db")
                    db_url = f"sqlite+aiosqlite:///{sqlite_path}"
                    logger.warning(f"[DATABASE] Localhost PostgreSQL not reachable. Falling back to SQLite: {db_url}")
            except Exception:
                pass
            finally:
                sock.close()

        connect_args = {}
        # SQLite async requires check_same_thread=False
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            db_url,
            echo=settings.DEBUG and not settings.ENVIRONMENT == "production",
            future=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing an async database session per request."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """Execute a lightweight query to verify active database connectivity."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        return False

