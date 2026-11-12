import asyncio
import os
import sys

# Set DATABASE_URL to SQLite before importing app modules
db_file = os.path.abspath(r'X:\hackathon\Veritas\veritas.db').replace('\\', '/')
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"

sys.path.insert(0, r'X:\hackathon\Veritas\backend')

from app.core.database import get_engine, get_session_factory
from app.core.models.user import User
from app.core.security import hash_password
from sqlalchemy import select
import uuid

async def test_user():
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Check if user already exists
        res = await session.execute(select(User).where(User.email == "tester@veritas.local"))
        user = res.scalar_one_or_none()
        if user:
            print("User already exists:", user.email, "id:", user.id)
        else:
            new_user = User(
                id=uuid.uuid4(),
                email="tester@veritas.local",
                password_hash=hash_password("DevPassword123!"),
                full_name="Veritas QA Tester",
                is_active=True,
                is_verified=True,
            )
            session.add(new_user)
            await session.commit()
            print("Created tester user in SQLite:", new_user.email, "id:", new_user.id)

asyncio.run(test_user())
