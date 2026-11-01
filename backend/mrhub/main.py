"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from mrhub.api.routes.agent import router as agent_router
from mrhub.api.routes.approvals import router as approvals_router
from mrhub.api.routes.auth import router as auth_router
from mrhub.api.routes.capabilities import router as capabilities_router
from mrhub.api.routes.health import router as health_router
from mrhub.api.routes.jobs import router as jobs_router
from mrhub.api.routes.models import router as models_router
from mrhub.api.routes.policy import router as policy_router
from mrhub.api.routes.tasks import router as tasks_router
from mrhub.api.routes.tools import router as tools_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.auth import LoginAttemptLimiter


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Initialize persistent storage before serving requests."""
        TaskRepository(settings.database_path).initialize()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Local-first modular AI workspace API",
        lifespan=lifespan,
    )

    app.state.login_attempt_limiter = LoginAttemptLimiter()

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(capabilities_router)
    app.include_router(tasks_router)
    app.include_router(jobs_router)
    app.include_router(policy_router)
    app.include_router(models_router)
    app.include_router(tools_router)
    app.include_router(agent_router)
    return app


app = create_app()
