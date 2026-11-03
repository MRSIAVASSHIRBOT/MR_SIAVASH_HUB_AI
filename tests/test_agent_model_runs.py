import base64
import json

from client_helpers import authenticated_client, run_worker_once
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.idempotency import IdempotencyRepository
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.providers.base import ProviderHealth, ProviderRequest, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRouter


class ScriptedProvider:
    descriptor = ModelDescriptor(
        provider="test-local",
        model="scripted-agent",
        capability=ModelCapability(text=True),
        available=True,
        local=True,
        priority=1,
    )

    def __init__(self, output: str | None = None, error: Exception | None = None):
        self.output = output or json.dumps({"type": "final", "answer": "Durable answer"})
        self.error = error
        self.calls = 0

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=self.output,
        )

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        return ProviderHealth(available=True, reason_code="test_ready")


def _router(provider: ScriptedProvider) -> ModelRouter:
    router = ModelRouter()
    router.register_provider(provider)
    return router


def test_queued_model_run_is_encrypted_idempotent_and_worker_executed(monkeypatch):
    client = authenticated_client()
    provider = ScriptedProvider()
    router = _router(provider)
    monkeypatch.setattr(
        "mrhub.api.routes.agent_model_runs.build_model_router",
        lambda **kwargs: router,
    )
    monkeypatch.setattr(
        "mrhub.jobs.model_run_dispatch.build_model_router",
        lambda **kwargs: router,
    )

    payload = {
        "goal": "Return a durable answer.",
        "provider_mode": "local",
        "include_memory": False,
        "include_knowledge": False,
        "max_turns": 1,
        "max_output_tokens": 64,
    }
    headers = {"Idempotency-Key": "durable-run-001"}
    submitted = client.post("/agent/model-runs", json=payload, headers=headers)
    assert submitted.status_code == 202
    accepted = submitted.json()
    assert accepted["status"] == "queued"
    assert provider.calls == 0

    repeated = client.post("/agent/model-runs", json=payload, headers=headers)
    assert repeated.status_code == 202
    assert repeated.json()["workflow_id"] == accepted["workflow_id"]
    assert repeated.json()["idempotent_replay"] is True

    repository = TaskRepository(get_settings().database_path)
    recovery = WorkflowRecoveryRepository(get_settings().database_path)
    stored = recovery.get_encrypted_payload(
        __import__("uuid").UUID(accepted["workflow_id"]),
        owner_user_id="owner",
    )
    assert stored is not None
    assert "Return a durable answer" not in stored["ciphertext_b64"]
    assert stored["ciphertext_b64"] != ""

    worker_result = run_worker_once()
    assert worker_result is not None
    assert worker_result.status.value == "succeeded"
    assert provider.calls == 1

    completed = client.get(f"/agent/model-runs/{accepted['workflow_id']}")
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "succeeded"
    assert body["result"]["execution"]["answer"] == "Durable answer"
    assert body["result"]["execution"]["status"] == "completed"

    idempotency = IdempotencyRepository(get_settings().database_path).get(
        "agent.model_run:owner", "durable-run-001"
    )
    assert idempotency is not None
    assert idempotency.status == "completed"


def test_interrupted_model_run_is_unknown_outcome_and_not_replayed(monkeypatch):
    client = authenticated_client()
    provider = ScriptedProvider(error=RuntimeError("ambiguous provider interruption"))
    router = _router(provider)
    monkeypatch.setattr(
        "mrhub.api.routes.agent_model_runs.build_model_router",
        lambda **kwargs: router,
    )
    monkeypatch.setattr(
        "mrhub.jobs.model_run_dispatch.build_model_router",
        lambda **kwargs: router,
    )

    submitted = client.post(
        "/agent/model-runs",
        headers={"Idempotency-Key": "durable-run-unknown"},
        json={
            "goal": "Exercise conservative recovery.",
            "provider_mode": "local",
            "include_memory": False,
            "include_knowledge": False,
            "max_turns": 1,
            "max_output_tokens": 64,
        },
    )
    assert submitted.status_code == 202
    workflow_id = submitted.json()["workflow_id"]

    worker_result = run_worker_once()
    assert worker_result is not None
    assert worker_result.status.value == "waiting_approval"
    assert provider.calls == 1

    run = WorkflowRecoveryRepository(get_settings().database_path).get_run(
        __import__("uuid").UUID(workflow_id), owner_user_id="owner"
    )
    assert run is not None
    assert run["status"] == "recovery_required"
    assert run["steps"][0]["status"] == "unknown_outcome"

    reservation = IdempotencyRepository(get_settings().database_path).get(
        "agent.model_run:owner", "durable-run-unknown"
    )
    assert reservation is not None
    assert reservation.status == "unknown_outcome"
    assert provider.calls == 1
