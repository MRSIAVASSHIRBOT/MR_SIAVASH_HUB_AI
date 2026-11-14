"""FastAPI application entry point. Project attribution: MR_SIAVASH_IR_BOT."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from mrhub.api.routes.agent import router as agent_router
from mrhub.api.routes.agent_context import router as agent_context_router
from mrhub.api.routes.agent_model_runs import router as agent_model_runs_router
from mrhub.api.routes.agent_proposals import router as agent_proposals_router
from mrhub.api.routes.agent_run import router as agent_run_router
from mrhub.api.routes.approvals import router as approvals_router
from mrhub.api.routes.auth import router as auth_router
from mrhub.api.routes.capabilities import router as capabilities_router
from mrhub.api.routes.content import router as content_router
from mrhub.api.routes.content_schedules import router as content_schedules_router
from mrhub.api.routes.health import router as health_router
from mrhub.api.routes.jobs import router as jobs_router
from mrhub.api.routes.knowledge import router as knowledge_router
from mrhub.api.routes.knowledge_evaluation import router as knowledge_evaluation_router
from mrhub.api.routes.media import router as media_router
from mrhub.api.routes.memory import router as memory_router
from mrhub.api.routes.models import router as models_router
from mrhub.api.routes.nexus import router as nexus_router
from mrhub.api.routes.policy import router as policy_router
from mrhub.api.routes.platform import router as platform_router
from mrhub.api.routes.research import router as research_router
from mrhub.api.routes.projects import router as projects_router
from mrhub.api.routes.public_media import router as public_media_router
from mrhub.api.routes.security_lab import router as security_lab_router
from mrhub.api.routes.tasks import router as tasks_router
from mrhub.api.routes.telegram_integration import router as telegram_integration_router
from mrhub.api.routes.tools import router as tools_router
from mrhub.api.routes.video_intelligence import router as video_intelligence_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.integrations.assistant_gateway import router as assistant_gateway_router
from mrhub.integrations.code_engine import router as code_engine_router
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
        description="Local-first modular AI workspace API. Project attribution: MR_SIAVASH_IR_BOT.",
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
    app.include_router(assistant_gateway_router)
    app.include_router(code_engine_router)
    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(capabilities_router)
    app.include_router(content_router)
    app.include_router(content_schedules_router)
    app.include_router(tasks_router)
    app.include_router(telegram_integration_router)
    app.include_router(jobs_router)
    app.include_router(knowledge_router)
    app.include_router(knowledge_evaluation_router)
    app.include_router(policy_router)
    app.include_router(platform_router)
    app.include_router(research_router)
    app.include_router(projects_router)
    app.include_router(models_router)
    app.include_router(nexus_router)
    app.include_router(memory_router)
    app.include_router(media_router)
    app.include_router(public_media_router)
    app.include_router(security_lab_router)
    app.include_router(tools_router)
    app.include_router(video_intelligence_router)
    app.include_router(agent_router)
    app.include_router(agent_context_router)
    app.include_router(agent_run_router)
    app.include_router(agent_model_runs_router)
    app.include_router(agent_proposals_router)
    app.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).resolve().parent / "web", html=True),
        name="operator-ui",
    )
    return app


app = create_app()
