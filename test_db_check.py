import asyncio
import os
import sys

db_file = os.path.abspath(r'X:\hackathon\Veritas\veritas.db').replace('\\', '/')
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
sys.path.insert(0, r'X:\hackathon\Veritas\backend')

from app.core.database import check_database_connection

async def test():
    res = await check_database_connection()
    print("Database connection result:", res)

asyncio.run(test())
