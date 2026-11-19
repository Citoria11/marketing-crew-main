"""SQLAlchemy async engine + session factory for PostgreSQL.

Usage
-----
Import ``AsyncSessionLocal`` and use it as an async context manager::

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Campaign))

Or use the ``get_db`` FastAPI dependency::

    @app.get("/campaigns")
    async def list_campaigns(db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

# ---------------------------------------------------------------------------
# Connection URL
# ---------------------------------------------------------------------------
# Override ``DATABASE_URL`` in the environment to point at a real Postgres
# instance.  The default targets a local dev database.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/marketing_crew",
)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=bool(os.getenv("SQLALCHEMY_ECHO", "")),
    future=True,
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session and close it when the request is done."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Schema initialisation helper (for dev / tests)
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables defined in the SQLAlchemy metadata.

    Call this once at application start-up or from a migration script.
    In production prefer Alembic migrations over ``create_all``.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
