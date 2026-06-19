"""
FastAPI application factory and entry point.

Configures middleware, routers, exception handlers, and serves as the
ASGI application object that uvicorn runs.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core import logging  # noqa: F401  — initialises structlog on import
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.middleware.RequestLoggingMiddleware import RequestLoggingMiddleware

app = FastAPI(
    title="Learning Platform API",
    description="A production-grade synchronous FastAPI backend for an online learning platform.",
    version="1.0.0",
    openapi_url=f"/{settings.APP_PREFIX}/v1/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

# ── Middleware (order matters — outermost first) ─────────────────────────
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────────────
app.include_router(api_router, prefix=f"/{settings.APP_PREFIX}/v1")

# ── Exception Handlers ───────────────────────────────────────────────────
register_exception_handlers(app)


@app.get("/health", tags=["health"])
def health_check():
    """Liveness probe for load balancers and orchestrators."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
