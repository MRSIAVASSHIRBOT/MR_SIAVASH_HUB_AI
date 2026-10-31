from uuid import uuid4

import pytest

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import InvalidTaskTransition, JobEngine
from mrhub.providers.router import (
    ModelCapability, ModelDescriptor, ModelRequest, ModelRouter,
)
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine


def test_policy_denies_prohibited_actions() -> None:
    result = PolicyEngine().evaluate(ActionRequest(
        action="security.prohibited",
        risk_class=RiskClass.PROHIBITED,
    ))
    assert result.decision is PolicyDecision.DENY


def test_policy_requires_approval_for_high_impact() -> None:
    engine = PolicyEngine()
    pending = engine.evaluate(ActionRequest(
        action="publishing.post",
        risk_class=RiskClass.HIGH,
        external_side_effect=True,
    ))
    approved = engine.evaluate(ActionRequest(
        action="publishing.post",
        risk_class=RiskClass.HIGH,
        external_side_effect=True,
        user_approved=True,
    ))
    assert pending.decision is PolicyDecision.REQUIRE_APPROVAL
    assert approved.decision is PolicyDecision.ALLOW


def test_policy_denies_missing_permission() -> None:
    result = PolicyEngine().evaluate(ActionRequest(
        action="files.write",
        risk_class=RiskClass.MODERATE,
        required_permissions=frozenset({"workspace.files.write"}),
    ))
    assert result.decision is PolicyDecision.DENY


def test_job_engine_lifecycle_and_terminal_state(tmp_path) -> None:
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    repository.initialize()
    engine = JobEngine(repository)
    task = engine.submit(TaskRecord(task_type="test.task"))
    running = engine.transition(task.task_id, TaskStatus.RUNNING)
    assert running.status is TaskStatus.RUNNING
    cancelled = engine.cancel(task.task_id)
    assert cancelled.status is TaskStatus.CANCELLED
    with pytest.raises(InvalidTaskTransition):
        engine.transition(task.task_id, TaskStatus.RUNNING)


def test_job_engine_not_found(tmp_path) -> None:
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    repository.initialize()
    with pytest.raises(KeyError):
        JobEngine(repository).cancel(uuid4())


def test_model_router_selects_capable_local_model() -> None:
    router = ModelRouter()
    router.register(ModelDescriptor(
        provider="cloud", model="vision-large",
        capability=ModelCapability(vision=True), priority=1,
    ))
    router.register(ModelDescriptor(
        provider="local", model="vision-small",
        capability=ModelCapability(vision=True), local=True, priority=10,
    ))
    selection = router.select(ModelRequest(requires_vision=True, prefer_local=True))
    assert selection.provider == "local"
    assert selection.model == "vision-small"


def test_model_router_rejects_unsupported_capability() -> None:
    router = ModelRouter()
    router.register(ModelDescriptor(
        provider="mock", model="text-only", capability=ModelCapability(),
    ))
    with pytest.raises(LookupError):
        router.select(ModelRequest(requires_audio=True))
