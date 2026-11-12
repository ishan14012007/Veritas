import asyncio
import os
import sys

sys.path.insert(0, r'X:\hackathon\Veritas\backend')

from sqlalchemy.ext.asyncio import create_async_engine
from app.core.models.base import Base

# Import all models to register with Base.metadata
import app.core.models.user
import app.core.models.organization
import app.core.models.audit
import app.accord.models.conversation
import app.accord.models.message
import app.accord.models.participant
import app.accord.models.agreement
import app.accord.models.obligation
import app.accord.models.financial_fact
import app.accord.models.expense_split
import app.accord.models.ambiguity
import app.accord.models.analysis
import app.payments.models
import app.whatsapp.models

async def init_sqlite():
    db_path = r'X:\hackathon\Veritas\veritas.db'
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        print("Creating all tables for VERITAS on SQLite...")
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully!")
    print("Registered tables:", list(Base.metadata.tables.keys()))
    await engine.dispose()

asyncio.run(init_sqlite())
