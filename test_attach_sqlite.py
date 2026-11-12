import asyncio
import os
import sys

db_file = os.path.abspath(r'X:\hackathon\Veritas\veritas.db').replace('\\', '/')
sys.path.insert(0, r'X:\hackathon\Veritas\backend')

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, event
from app.core.models.user import User
from app.core.models.base import Base
from app.core.security import hash_password
import uuid

async def test_async_sqlite():
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def attach_schemas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"ATTACH DATABASE '{db_file}' AS core;")
        cursor.execute(f"ATTACH DATABASE '{db_file}' AS accord;")
        cursor.close()

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if user already exists
        res = await session.execute(select(User).where(User.email == "tester@veritas.local"))
        user = res.scalar_one_or_none()
        if user:
            print("Existing user found:", user.email, "id:", user.id)
        else:
            new_user = User(
                id=uuid.uuid4(),
                email="tester@veritas.local",
                password_hash=hash_password("TesterPass123!"),
                full_name="Veritas QA Tester",
                is_active=True,
                is_verified=True,
            )
            session.add(new_user)
            await session.commit()
            print("Successfully created tester user in SQLite:", new_user.email, "id:", new_user.id)

    await engine.dispose()

asyncio.run(test_async_sqlite())
