import json
from pathlib import Path

from client_helpers import authenticated_client


def test_synthetic_knowledge_retrieval_corpus_returns_expected_source_at_rank_one() -> None:
    cases = json.loads(Path(__file__).with_name("knowledge_eval.json").read_text(encoding="utf-8"))
    client = authenticated_client()
    for case in cases:
        created = client.post(
            "/knowledge/documents",
            json={"title": case["title"], "content": case["content"]},
        )
        assert created.status_code == 201

    for case in cases:
        response = client.post("/knowledge/search", json={"query": case["query"], "limit": 5})
        assert response.status_code == 200
        results = response.json()["results"]
        assert results, f"No result for evaluation query: {case['query']}"
        assert results[0]["title"] == case["expected_title"], (
            f"Expected {case['expected_title']!r} at rank 1 for {case['query']!r}, "
            f"got {results[0]['title']!r}"
        )
        assert results[0]["citation_ref"].startswith("knowledge://documents/")
