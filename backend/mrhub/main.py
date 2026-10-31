"""FastAPI application entry point."""

from fastapi import FastAPI

from mrhub.api.routes.approvals import router as approvals_router
from mrhub.api.routes.auth import router as auth_router
from mrhub.api.routes.health import router as health_router
from mrhub.api.routes.jobs import router as jobs_router
from mrhub.api.routes.models import router as models_router
from mrhub.api.routes.policy import router as policy_router
from mrhub.api.routes.tasks import router as tasks_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Local-first modular AI workspace API",
    )

    @app.on_event("startup")
    def initialize_storage() -> None:
        TaskRepository(settings.database_path).initialize()

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(tasks_router)
    app.include_router(jobs_router)
    app.include_router(policy_router)
    app.include_router(models_router)
    return app


app = create_app()
