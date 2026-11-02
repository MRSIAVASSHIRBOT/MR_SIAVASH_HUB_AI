import json

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
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

    def __init__(self, output: str):
        self.output = output
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=self.output,
        )

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        return ProviderHealth(available=True, reason_code="test_ready")


def test_agent_run_uses_owner_scoped_context_and_returns_freshness_citations(monkeypatch):
    client = authenticated_client()
    document = client.post(
        "/knowledge/documents",
        json={
            "title": "Agent Context Fixture",
            "content": "agent freshness test evidence for citations and source status",
            "source_ref": "local-note:agent-context-fixture",
        },
    )
    assert document.status_code == 201
    doc = document.json()
    marked = client.patch(
        f"/knowledge/sources/{doc['source_id']}/freshness",
        json={"status": "stale"},
    )
    assert marked.status_code == 200

    citation = f"knowledge://documents/{doc['document_id']}#chunk-0"
    provider = ScriptedProvider(json.dumps({
        "type": "final",
        "answer": f"The evidence is marked stale; citation: {citation}",
    }))
    router = ModelRouter()
    router.register_provider(provider)
    monkeypatch.setattr(
        "mrhub.api.routes.agent_run.build_model_router",
        lambda **kwargs: router,
    )

    response = client.post(
        "/agent/run",
        json={
            "goal": "Summarize evidence and cite the reference.",
            "context_query": "agent freshness test",
            "provider_mode": "local",
            "include_memory": False,
            "include_knowledge": True,
            "max_turns": 2,
            "max_output_tokens": 128,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution"]["status"] == "completed"
    assert citation in body["execution"]["answer"]
    source = next(item for item in body["context_sources"] if item["reference"] == citation)
    assert source["freshness_status"] == "stale"
    assert source["trust_classification"] == "user_supplied"
    assert "freshness_status" in provider.requests[0].input_text
    assert citation in provider.requests[0].input_text

    repository = TaskRepository(get_settings().database_path)
    with repository._connection() as connection:
        audit = connection.execute(
            "SELECT metadata_json FROM audit_events WHERE event_type = 'agent.model_run' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert "Summarize evidence" not in audit["metadata_json"]


def test_agent_run_fails_closed_when_requested_provider_is_not_configured(monkeypatch):
    client = authenticated_client()
    empty_router = ModelRouter()
    monkeypatch.setattr(
        "mrhub.api.routes.agent_run.build_model_router",
        lambda **kwargs: empty_router,
    )

    response = client.post(
        "/agent/run",
        json={
            "goal": "Run only if the requested provider exists.",
            "provider_mode": "remote",
        },
    )
    assert response.status_code == 503
    assert "remote inference provider" in response.json()["detail"]
