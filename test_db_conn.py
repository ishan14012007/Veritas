import asyncio
import os
import sys

sys.path.insert(0, r'X:\hackathon\Veritas\backend')
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///X:/hackathon/Veritas/veritas.db"

from app.core.database import check_database_connection, get_db

async def test_conn():
    res = await check_database_connection()
    print("Database connection check result:", res)
    async for db in get_db():
        from sqlalchemy import text
        r = await db.execute(text("SELECT count(*) FROM users;"))
        count = r.scalar()
        print("Users count:", count)
        break

asyncio.run(test_conn())
