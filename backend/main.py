"""FastAPI application entry point.

Mounts the three route groups and wires up startup / middleware.
Route logic lives in routes/; DB models in db/; agents in agents/; graph in workflow/.
"""
from __future__ import annotations

import logging
import logging.config
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from workflow.config import close_checkpointer, init_checkpointer
from workflow.graph import build_graph, set_graph
from routes.campaigns import router as campaigns_router
from routes.chat import router as chat_router
from routes.upload import router as upload_router
from routes.workflow_routes import router as workflow_router

# ---------------------------------------------------------------------------
# Logging — configure before any module that uses getLogger(__name__)
# ---------------------------------------------------------------------------
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {"level": os.getenv("LOG_LEVEL", "INFO"), "handlers": ["console"]},
    "loggers": {
        "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
        "httpx": {"level": "WARNING", "propagate": True},
        "openai": {"level": "WARNING", "propagate": True},
        "google": {"level": "WARNING", "propagate": True},
    },
})

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup -------------------------------------------------------------
    logger.info("Starting up Country Music Band AI Platform")
    try:
        await init_db()
        logger.info("Database tables verified")
    except Exception as exc:  # noqa: BLE001
        logger.warning("init_db skipped (use Alembic migrations in production): %s", exc)

    checkpointer = await init_checkpointer()
    set_graph(build_graph(checkpointer))
    logger.info("LangGraph compiled and ready")

    yield

    # ---- Shutdown ------------------------------------------------------------
    logger.info("Shutting down — closing checkpointer pool")
    await close_checkpointer()


app = FastAPI(
    title="Country Music Band AI Platform",
    description="Production-grade AI platform for managing country music campaigns.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:4000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request with method, path, status code, and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/health", tags=["system"], summary="Health check.")
async def health() -> dict:
    """Returns 200 OK when the service is running."""
    return {"status": "ok", "service": "marketing-crew-backend"}


app.include_router(upload_router)
app.include_router(campaigns_router)
app.include_router(workflow_router)
app.include_router(chat_router)
