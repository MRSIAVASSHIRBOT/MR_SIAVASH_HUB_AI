"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from mrhub.api.routes.agent import router as agent_router
from mrhub.api.routes.approvals import router as approvals_router
from mrhub.api.routes.auth import router as auth_router
from mrhub.api.routes.capabilities import router as capabilities_router
from mrhub.api.routes.content import router as content_router
from mrhub.api.routes.health import router as health_router
from mrhub.api.routes.jobs import router as jobs_router
from mrhub.api.routes.knowledge import router as knowledge_router
from mrhub.api.routes.media import router as media_router
from mrhub.api.routes.memory import router as memory_router
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
        if request.url.path == "/ui" or request.url.path.startswith("/ui/"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(capabilities_router)
    app.include_router(content_router)
    app.include_router(tasks_router)
    app.include_router(jobs_router)
    app.include_router(knowledge_router)
    app.include_router(policy_router)
    app.include_router(models_router)
    app.include_router(memory_router)
    app.include_router(media_router)
    app.include_router(tools_router)
    app.include_router(agent_router)
    app.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).resolve().parent / "web", html=True),
        name="operator-ui",
    )
    return app


app = create_app()
