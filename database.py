# """
# Async Database Engine & Connection Pool Configuration
# Sized for high concurrent traffic (100+ concurrent users).
# """

# import os
# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# from dotenv import load_dotenv
# from models import Base

# load_dotenv()

# DATABASE_URL = os.getenv("DATABASE_URL")

# # Provide seamless local SQLite support when DATABASE_URL is not configured
# if not DATABASE_URL:
#     DATABASE_URL = "sqlite+aiosqlite:///./jobaccess.db"
# elif DATABASE_URL.startswith("postgresql://"):
#     DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
# elif DATABASE_URL.startswith("postgres://"):
#     DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# is_sqlite = DATABASE_URL.startswith("sqlite")

# engine = create_async_engine(
#     DATABASE_URL,
#     echo=False,
#     connect_args={"check_same_thread": False} if is_sqlite else {},
#     **({} if is_sqlite else {
#         "pool_size": 30,
#         "max_overflow": 70,
#         "pool_timeout": 30,
#         "pool_recycle": 1800,
#         "pool_pre_ping": True,
#     })
# )

# AsyncSessionLocal = async_sessionmaker(
#     bind=engine,
#     class_=AsyncSession,
#     expire_on_commit=False,
#     autoflush=False,
# )

# async def get_db():
#     """Dependency for obtaining async DB sessions with auto-closing."""
#     async with AsyncSessionLocal() as session:
#         try:
#             yield session
#         except Exception:
#             await session.rollback()
#             raise
#         finally:
#             await session.close()

# async def init_db():
#     """Create tables if they don't exist."""
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)















"""
Async Database Engine & Connection Pool Configuration
Sized for high concurrent traffic (100+ concurrent users).
"""

import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, text
from sqlalchemy.orm import load_only
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv
from models import Base, Job

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Provide seamless local SQLite support when DATABASE_URL is not configured
if not DATABASE_URL:
    DATABASE_URL = "sqlite+aiosqlite:///./jobaccess.db"
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if is_sqlite else {},
    **({} if is_sqlite else {
        # Reduced from 30/70: up to 100 connections can exhaust a Neon database.
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    })
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db():
    """Dependency for obtaining async DB sessions with auto-closing."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Create tables if they don't exist, then apply additive migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if not is_sqlite:
            # Apply method (link / phone / both) columns for existing databases
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apply_method VARCHAR(10) NOT NULL DEFAULT 'link'"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_phone VARCHAR(30)"))
            await conn.execute(text("ALTER TABLE jobs ALTER COLUMN application_url DROP NOT NULL"))
            # Speed-up indexes
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_status_deadline ON jobs (status, deadline)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC)"))


# ---------------------------------------------------------------------------
# Deadline helpers (deadlines are stored as YYYY-MM-DD strings)
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))

def today_ist() -> str:
    """Today's date in IST as YYYY-MM-DD (matches how deadlines are stored)."""
    return datetime.now(IST).date().isoformat()

async def delete_expired_jobs() -> int:
    """Delete jobs whose deadline is before today. Jobs stay live through the deadline day."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Job)
            .options(load_only(Job.id))
            .where(func.length(Job.deadline) == 10, Job.deadline < today_ist())
        )
        expired = res.scalars().all()
        for job in expired:
            await db.delete(job)
        if expired:
            await db.commit()
        return len(expired)