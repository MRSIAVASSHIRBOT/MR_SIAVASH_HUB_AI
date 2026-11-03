"""Source freshness propagation through the untrusted Agent context boundary."""

import pytest

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



class MixedFreshnessKnowledge:
    def search(self, owner_user_id: str, query: str, limit: int):
        return [
            {
                "citation_ref": "knowledge://documents/stale#chunk-0",
                "source_ref": "local-note:stale",
                "trust_classification": "user_supplied",
                "freshness_status": "stale",
                "freshness_checked_at": "2026-11-02T00:00:00+00:00",
                "document_hash": "a" * 64,
                "chunk_hash": "b" * 64,
                "content": "stale evidence",
            },
            {
                "citation_ref": "knowledge://documents/unknown#chunk-0",
                "source_ref": "local-note:unknown",
                "trust_classification": "user_supplied",
                "freshness_status": "unknown",
                "freshness_checked_at": None,
                "document_hash": "c" * 64,
                "chunk_hash": "d" * 64,
                "content": "unknown evidence",
            },
            {
                "citation_ref": "knowledge://documents/current#chunk-0",
                "source_ref": "local-note:current",
                "trust_classification": "user_supplied",
                "freshness_status": "owner_reviewed_current",
                "freshness_checked_at": "2026-11-02T00:00:00+00:00",
                "document_hash": "e" * 64,
                "chunk_hash": "f" * 64,
                "content": "owner-reviewed evidence",
            },
            {
                "citation_ref": "knowledge://documents/missing-review-time#chunk-0",
                "source_ref": "local-note:missing-review-time",
                "trust_classification": "user_supplied",
                "freshness_status": "owner_reviewed_current",
                "freshness_checked_at": None,
                "document_hash": "1" * 64,
                "chunk_hash": "2" * 64,
                "content": "evidence missing a review timestamp",
            },
        ]


def test_current_only_policy_excludes_stale_and_unreviewed_knowledge():
    assembler = AgentContextAssembler.__new__(AgentContextAssembler)
    assembler.memory = EmptyMemory()
    assembler.knowledge = MixedFreshnessKnowledge()

    result = assembler.assemble(
        "owner-a",
        query="review",
        include_memory=False,
        include_knowledge=True,
        knowledge_freshness_policy="owner_reviewed_current_only",
    )

    assert [item["reference"] for item in result["passages"]] == [
        "knowledge://documents/current#chunk-0"
    ]
    assert result["knowledge_freshness_policy"] == "owner_reviewed_current_only"
    assert result["excluded_stale_knowledge_count"] == 1
    assert result["excluded_unreviewed_knowledge_count"] == 2
    assert "stale evidence" not in result["context_block"]
    assert "unknown evidence" not in result["context_block"]
    assert "owner-reviewed evidence" in result["context_block"]
    assert result["passages"][0]["freshness_is_automatically_verified"] is False


def test_context_rejects_unknown_freshness_policy():
    assembler = AgentContextAssembler.__new__(AgentContextAssembler)
    assembler.memory = EmptyMemory()
    assembler.knowledge = EmptyMemory()

    with pytest.raises(ValueError, match="Unsupported knowledge freshness policy"):
        assembler.assemble(
            "owner-a",
            query="review",
            knowledge_freshness_policy="automatically_verified",
        )



class ManyStaleThenCurrentKnowledge:
    def search(self, owner_user_id: str, query: str, limit: int):
        assert limit == 25
        results = []
        for index in range(4):
            results.append({
                "citation_ref": f"knowledge://documents/stale-{index}#chunk-0",
                "source_ref": f"local-note:stale-{index}",
                "trust_classification": "user_supplied",
                "freshness_status": "stale",
                "freshness_checked_at": "2026-11-02T00:00:00+00:00",
                "document_hash": "a" * 64,
                "chunk_hash": "b" * 64,
                "content": "stale result",
            })
        results.append({
            "citation_ref": "knowledge://documents/current-after-stale#chunk-0",
            "source_ref": "local-note:current",
            "trust_classification": "user_supplied",
            "freshness_status": "owner_reviewed_current",
            "freshness_checked_at": "2026-11-02T00:00:00+00:00",
            "document_hash": "c" * 64,
            "chunk_hash": "d" * 64,
            "content": "current result after stale candidates",
        })
        return results


def test_current_only_policy_searches_past_the_default_four_chunk_limit():
    assembler = AgentContextAssembler.__new__(AgentContextAssembler)
    assembler.memory = EmptyMemory()
    assembler.knowledge = ManyStaleThenCurrentKnowledge()

    result = assembler.assemble(
        "owner-a",
        query="review",
        include_memory=False,
        include_knowledge=True,
        knowledge_freshness_policy="owner_reviewed_current_only",
    )

    assert len(result["passages"]) == 1
    assert result["passages"][0]["reference"] == (
        "knowledge://documents/current-after-stale#chunk-0"
    )
    assert result["excluded_stale_knowledge_count"] == 4
    assert result["excluded_unreviewed_knowledge_count"] == 0



class AtCandidateLimitKnowledge:
    def search(self, owner_user_id: str, query: str, limit: int):
        assert limit == 25
        return [
            {
                "citation_ref": f"knowledge://documents/stale-{index}#chunk-0",
                "source_ref": f"local-note:stale-{index}",
                "trust_classification": "user_supplied",
                "freshness_status": "stale",
                "freshness_checked_at": "2026-11-02T00:00:00+00:00",
                "document_hash": "a" * 64,
                "chunk_hash": "b" * 64,
                "content": "stale candidate",
            }
            for index in range(limit)
        ]


def test_current_only_policy_reports_when_candidate_search_reaches_its_bound():
    assembler = AgentContextAssembler.__new__(AgentContextAssembler)
    assembler.memory = EmptyMemory()
    assembler.knowledge = AtCandidateLimitKnowledge()

    result = assembler.assemble(
        "owner-a",
        query="review",
        include_memory=False,
        include_knowledge=True,
        knowledge_freshness_policy="owner_reviewed_current_only",
    )

    assert result["knowledge_candidates_scanned"] == 25
    assert result["knowledge_candidate_limit"] == 25
    assert result["knowledge_candidates_may_be_truncated"] is True
    assert result["excluded_stale_knowledge_count"] == 25
    assert result["passages"] == []


def test_context_reports_disabled_knowledge_retrieval_without_truncation():
    assembler = AgentContextAssembler.__new__(AgentContextAssembler)
    assembler.memory = EmptyMemory()
    assembler.knowledge = EmptyMemory()

    result = assembler.assemble(
        "owner-a",
        query="review",
        include_memory=False,
        include_knowledge=False,
    )

    assert result["knowledge_candidates_scanned"] == 0
    assert result["knowledge_candidate_limit"] == 0
    assert result["knowledge_candidates_may_be_truncated"] is False
