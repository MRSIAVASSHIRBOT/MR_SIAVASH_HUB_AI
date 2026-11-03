import json
from uuid import UUID

from client_helpers import authenticated_client, run_worker_once
from mrhub.config import get_settings
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
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        self.requests.append(request)
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

    recovery = WorkflowRecoveryRepository(get_settings().database_path)
    stored = recovery.get_encrypted_payload(
        UUID(accepted["workflow_id"]),
        owner_user_id="local-owner",
    )
    assert stored is not None
    assert "Return a durable answer" not in stored["ciphertext_b64"]
    assert stored["ciphertext_b64"] != ""

    worker_result = run_worker_once()
    assert worker_result is not None
    assert worker_result.status.value == "succeeded"
    assert provider.calls == 1

    completed = client.get(f"/agent/model-run-workflows/{accepted['workflow_id']}")
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "succeeded"
    assert body["result"]["execution"]["answer"] == "Durable answer"
    assert body["result"]["execution"]["status"] == "completed"

    idempotency = IdempotencyRepository(get_settings().database_path).get(
        "agent.model_run:local-owner", "durable-run-001"
    )
    assert idempotency is not None
    assert idempotency.status == "completed"



def test_queued_model_run_cancellation_is_owner_scoped_and_removes_request_ciphertext(monkeypatch):
    client = authenticated_client()
    router = _router(ScriptedProvider())
    monkeypatch.setattr(
        "mrhub.api.routes.agent_model_runs.build_model_router",
        lambda **kwargs: router,
    )
    submitted = client.post(
        "/agent/model-runs",
        headers={"Idempotency-Key": "durable-run-cancel"},
        json={
            "goal": "Cancel before worker claim.",
            "provider_mode": "local",
            "include_memory": False,
            "include_knowledge": False,
        },
    )
    assert submitted.status_code == 202
    workflow_id = UUID(submitted.json()["workflow_id"])

    recovery = WorkflowRecoveryRepository(get_settings().database_path)
    assert recovery.get_run(workflow_id, owner_user_id="another-owner") is None
    cancelled = client.post(f"/agent/model-run-workflows/{workflow_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert recovery.get_encrypted_payload(
        workflow_id, owner_user_id="local-owner"
    ) is None

    status = client.get(f"/agent/model-run-workflows/{workflow_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "cancelled"
    assert status.json()["result"] is None


def test_model_run_idempotency_key_rejects_a_different_request(monkeypatch):
    client = authenticated_client()
    router = _router(ScriptedProvider())
    monkeypatch.setattr(
        "mrhub.api.routes.agent_model_runs.build_model_router",
        lambda **kwargs: router,
    )
    headers = {"Idempotency-Key": "durable-run-conflict"}
    first = client.post(
        "/agent/model-runs",
        headers=headers,
        json={
            "goal": "First request.",
            "provider_mode": "local",
            "include_memory": False,
            "include_knowledge": False,
        },
    )
    assert first.status_code == 202
    second = client.post(
        "/agent/model-runs",
        headers=headers,
        json={
            "goal": "Different request.",
            "provider_mode": "local",
            "include_memory": False,
            "include_knowledge": False,
        },
    )
    assert second.status_code == 409


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
        UUID(workflow_id), owner_user_id="local-owner"
    )
    assert run is not None
    assert run["status"] == "recovery_required"
    assert run["steps"][0]["status"] == "unknown_outcome"

    reservation = IdempotencyRepository(get_settings().database_path).get(
        "agent.model_run:local-owner", "durable-run-unknown"
    )
    assert reservation is not None
    assert reservation.status == "unknown_outcome"
    assert provider.calls == 1


def test_durable_model_run_applies_owner_reviewed_knowledge_freshness_policy(monkeypatch):
    client = authenticated_client()
    document = client.post(
        "/knowledge/documents",
        json={
            "title": "Durable stale context fixture",
            "content": "durable stale evidence must not reach the model",
            "source_ref": "local-note:durable-stale-context",
        },
    )
    assert document.status_code == 201
    marked = client.patch(
        f"/knowledge/sources/{document.json()['source_id']}/freshness",
        json={"status": "stale"},
    )
    assert marked.status_code == 200

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

    submitted = client.post(
        "/agent/model-runs",
        headers={"Idempotency-Key": "durable-run-freshness-001"},
        json={
            "goal": "Use only manually reviewed current evidence.",
            "context_query": "durable stale evidence",
            "provider_mode": "local",
            "include_memory": False,
            "include_knowledge": True,
            "knowledge_freshness_policy": "owner_reviewed_current_only",
            "max_turns": 1,
            "max_output_tokens": 64,
        },
    )
    assert submitted.status_code == 202
    accepted = submitted.json()
    assert accepted["knowledge_freshness_policy"] == "owner_reviewed_current_only"
    assert accepted["context_passage_count"] == 0
    assert accepted["excluded_stale_knowledge_count"] == 1
    assert provider.calls == 0

    worker_result = run_worker_once()
    assert worker_result is not None
    assert worker_result.status.value == "succeeded"
    assert provider.calls == 1
    assert "durable stale evidence must not reach the model" not in (
        provider.requests[0].input_text
    )

    completed = client.get(
        f"/agent/model-run-workflows/{accepted['workflow_id']}"
    )
    assert completed.status_code == 200
    summary = completed.json()["result"]["context_summary"]
    assert summary["knowledge_freshness_policy"] == "owner_reviewed_current_only"
    assert summary["excluded_stale_knowledge_count"] == 1
    assert summary["excluded_unreviewed_knowledge_count"] == 0
    assert completed.json()["result"]["context_sources"] == []
