"""
FastAPI application factory.
New routers for each phase are added here — nothing else changes.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from core.config import settings
from core.metrics import REGISTRY
from api.routes import auth, health, tasks, chat, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing auto-created here — use `alembic upgrade head` instead.
    yield
    # Shutdown


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router)                              # GET /health
app.include_router(auth.router,  prefix="/api/auth",  tags=["auth"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router)                                # POST /api/chat, GET /api/chat/history, etc.
app.include_router(admin.router)                               # /api/admin/* (Phase 8)

# ── Prometheus Metrics (Phase 7) ──────────────────────────────────────────────
@app.get("/metrics", tags=["monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint for monitoring.

    Returns metrics in Prometheus text format.
    Exposes: queries answered, gaps detected, tasks created, tools deployed, test results.
    """
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

