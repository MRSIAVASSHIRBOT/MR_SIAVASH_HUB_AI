"""FastAPI application entry point. Project attribution: MR_SIAVASH_IR_BOT."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging import getLogger
from pathlib import Path
from time import perf_counter
from uuid import RFC_4122, UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from mrhub.agents.registry import build_default_agent_registry
from mrhub.agents.work_order_evidence import EvidenceVerifierRegistry
from mrhub.api.errors import (
    API_ERROR_RESPONSES,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from mrhub.api.routes.agent import router as agent_router
from mrhub.api.routes.agent_context import router as agent_context_router
from mrhub.api.routes.agent_model_runs import router as agent_model_runs_router
from mrhub.api.routes.agent_proposals import router as agent_proposals_router
from mrhub.api.routes.agent_registry import router as agent_registry_router
from mrhub.api.routes.agent_run import router as agent_run_router
from mrhub.api.routes.approvals import router as approvals_router
from mrhub.api.routes.auth import router as auth_router
from mrhub.api.routes.capabilities import router as capabilities_router
from mrhub.api.routes.content import router as content_router
from mrhub.api.routes.content_campaigns import router as content_campaigns_router
from mrhub.api.routes.content_schedules import router as content_schedules_router
from mrhub.api.routes.devices import router as devices_router
from mrhub.api.routes.health import router as health_router
from mrhub.api.routes.jobs import router as jobs_router
from mrhub.api.routes.knowledge import router as knowledge_router
from mrhub.api.routes.knowledge_evaluation import router as knowledge_evaluation_router
from mrhub.api.routes.media import router as media_router
from mrhub.api.routes.memory import router as memory_router
from mrhub.api.routes.models import router as models_router
from mrhub.api.routes.nexus import router as nexus_router
from mrhub.api.routes.platform import router as platform_router
from mrhub.api.routes.policy import router as policy_router
from mrhub.api.routes.projects import router as projects_router
from mrhub.api.routes.public_media import router as public_media_router
from mrhub.api.routes.research import router as research_router
from mrhub.api.routes.resource_reply import router as resource_reply_router
from mrhub.api.routes.security_lab import router as security_lab_router
from mrhub.api.routes.tasks import router as tasks_router
from mrhub.api.routes.telegram_integration import router as telegram_integration_router
from mrhub.api.routes.tools import router as tools_router
from mrhub.api.routes.video_intelligence import router as video_intelligence_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.infrastructure.request_metrics import RequestMetrics
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
    app.state.request_metrics = RequestMetrics()
    # The server-defined specialist catalog is frozen once at application composition.
    app.state.agent_registry = build_default_agent_registry()
    # Trusted adapters register only in server composition code; no HTTP route can register verifiers.
    app.state.work_order_evidence_verifiers = EvidenceVerifierRegistry()

    # Preserve legacy 'detail' fields while exposing a stable error envelope.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    def include_api_router(router) -> None:
        """Attach the common typed error contract to every mounted API router."""
        app.include_router(router, responses=API_ERROR_RESPONSES)


    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        supplied_request_id = request.headers.get("X-Request-ID", "")
        try:
            parsed_request_id = UUID(supplied_request_id)
            if (
                len(supplied_request_id) != 36
                or str(parsed_request_id) != supplied_request_id
                or parsed_request_id.version not in range(1, 9)
                or parsed_request_id.variant != RFC_4122
            ):
                raise ValueError("Request ID must be a canonical UUID")
            request_id = str(parsed_request_id)
        except (AttributeError, TypeError, ValueError):
            request_id = str(uuid4())

        supplied_correlation_id = request.headers.get("X-Correlation-ID", "")
        try:
            parsed_correlation_id = UUID(supplied_correlation_id)
            if (
                len(supplied_correlation_id) != 36
                or str(parsed_correlation_id) != supplied_correlation_id
                or parsed_correlation_id.version not in range(1, 9)
                or parsed_correlation_id.variant != RFC_4122
            ):
                raise ValueError("Correlation ID must be a canonical UUID")
            correlation_id = str(parsed_correlation_id)
        except (AttributeError, TypeError, ValueError):
            # Correlation metadata is diagnostic only; never trust or log invalid input.
            correlation_id = request_id

        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        started_at = perf_counter()
        response = await call_next(request)
        duration_ms = round(max(0.0, (perf_counter() - started_at) * 1000), 3)
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        outcome = "success" if response.status_code < 400 else "http_error"
        app.state.request_metrics.record(
            request.method, route_template, response.status_code, duration_ms
        )
        getLogger("mrhub.request").info(
            "http_request_completed request_id=%s correlation_id=%s method=%s route_template=%s status_code=%s duration_ms=%.3f outcome=%s",
            request_id,
            correlation_id,
            request.method,
            route_template,
            response.status_code,
            duration_ms,
            outcome,
            extra={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "method": request.method,
                "route_template": route_template,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "outcome": outcome,
            },
        )
        response.headers["X-Request-ID"] = request_id
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

    include_api_router(health_router)
    include_api_router(assistant_gateway_router)
    include_api_router(code_engine_router)
    include_api_router(auth_router)
    include_api_router(approvals_router)
    include_api_router(capabilities_router)
    include_api_router(content_router)
    include_api_router(devices_router)
    include_api_router(content_campaigns_router)
    include_api_router(content_schedules_router)
    include_api_router(tasks_router)
    include_api_router(telegram_integration_router)
    include_api_router(jobs_router)
    include_api_router(knowledge_router)
    include_api_router(knowledge_evaluation_router)
    include_api_router(policy_router)
    include_api_router(platform_router)
    include_api_router(research_router)
    include_api_router(projects_router)
    include_api_router(models_router)
    include_api_router(nexus_router)
    include_api_router(memory_router)
    include_api_router(media_router)
    include_api_router(public_media_router)
    include_api_router(resource_reply_router)
    include_api_router(security_lab_router)
    include_api_router(tools_router)
    include_api_router(video_intelligence_router)
    include_api_router(agent_router)
    include_api_router(agent_registry_router)
    include_api_router(agent_context_router)
    include_api_router(agent_run_router)
    include_api_router(agent_model_runs_router)
    include_api_router(agent_proposals_router)
    app.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).resolve().parent / "web", html=True),
        name="operator-ui",
    )
    return app


app = create_app()
