import asyncio
import os
import sys

sys.path.insert(0, r'X:\hackathon\Veritas\backend')

from app.core.config import get_settings
settings = get_settings()
db_file = os.path.abspath(r'X:\hackathon\Veritas\veritas.db').replace('\\', '/')
settings.DATABASE_URL = f"sqlite+aiosqlite:///{db_file}"

from app.core.database import check_database_connection, get_db
from app.core.models.base import Base
from app.core.models.user import User
from sqlalchemy import text, select

for table in Base.metadata.tables.values():
    table.schema = None

async def test():
    conn_ok = await check_database_connection()
    print("Database connection:", conn_ok)
    async for session in get_db():
        r = await session.execute(text("SELECT count(*) FROM users;"))
        print("Raw users count:", r.scalar())
        
        # Test ORM query
        res = await session.execute(select(User))
        users = res.scalars().all()
        print("ORM users count:", len(users))
        break

asyncio.run(test())
