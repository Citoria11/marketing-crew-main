"""AsyncPostgresSaver lifecycle for LangGraph checkpointing.

LangGraph's AsyncPostgresSaver stores all graph state directly in PostgreSQL,
replacing the manual LangGraphCheckpoint model. The Campaign table retains
only thread_id and workflow_status as lightweight linkage.

Requires psycopg3 (psycopg[binary]) and psycopg-pool.
The connection string must use plain postgresql:// (not +asyncpg).
"""
from __future__ import annotations

import os
from typing import Optional

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None


def _pg_connstr() -> str:
    """Convert SQLAlchemy-style DATABASE_URL to a psycopg3 connection string."""
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/marketing_crew",
    )
    # psycopg3 uses plain postgresql:// — strip the driver suffix
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )


async def init_checkpointer() -> AsyncPostgresSaver:
    """Open connection pool, create AsyncPostgresSaver, run schema setup.

    Must be called once inside the FastAPI lifespan startup block.
    Creates the ``checkpoints``, ``checkpoint_blobs``, and ``checkpoint_writes``
    tables in PostgreSQL if they do not already exist.
    """
    global _pool, _checkpointer
    _pool = AsyncConnectionPool(
        conninfo=_pg_connstr(),
        max_size=10,
        open=False,
        kwargs={"autocommit": True},
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the connection pool on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer not initialized. Ensure lifespan has run."
        )
    return _checkpointer
