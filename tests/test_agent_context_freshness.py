"""Source freshness propagation through the untrusted Agent context boundary."""

from mrhub.agents.context import AgentContextAssembler


class EmptyMemory:
    def search(self, owner_user_id: str, query: str, limit: int):
        return []


class StaleKnowledge:
    def search(self, owner_user_id: str, query: str, limit: int):
        return [{
            "citation_ref": "knowledge://documents/doc-1#chunk-0",
            "source_ref": "local-note:review",
            "trust_classification": "user_reviewed",
            "freshness_status": "stale",
            "freshness_checked_at": "2026-11-02T00:00:00+00:00",
            "document_hash": "a" * 64,
            "chunk_hash": "b" * 64,
            "content": "An evidence passage with a stale status.",
        }]


def test_context_preserves_stale_metadata_and_keeps_evidence_untrusted():
    assembler = AgentContextAssembler.__new__(AgentContextAssembler)
    assembler.memory = EmptyMemory()
    assembler.knowledge = StaleKnowledge()

    result = assembler.assemble(
        "owner-a",
        query="review",
        include_memory=False,
        include_knowledge=True,
    )

    passage = result["passages"][0]
    assert passage["freshness_status"] == "stale"
    assert passage["freshness_checked_at"] == "2026-11-02T00:00:00+00:00"
    assert passage["freshness_is_automatically_verified"] is False
    assert passage["content_is_untrusted_data"] is True
