from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_research_opportunity_evidence_and_assessment_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "web",
            "title": "Affordable website setup",
            "problem_statement": "Small local businesses struggle to launch and maintain a website.",
            "audience": "Small local businesses",
            "solution_hypothesis": "A guided website builder with managed maintenance.",
        })
        assert created.status_code == 201
        opportunity = created.json()
        assert opportunity["status"] == "new"
        assert opportunity["priority_score"] is None
        opportunity_id = opportunity["opportunity_id"]

        evidence = client.post(f"/research/opportunities/{opportunity_id}/evidence", json={
            "source_type": "public_discussion",
            "source_url": "https://example.com/community/thread-1",
            "source_label": "Public community thread",
            "observation_summary": "Several participants describe website setup as confusing and expensive.",
            "signal_strength": "high",
        })
        assert evidence.status_code == 201
        assert evidence.json()["canonical_url"] == "https://example.com/community/thread-1"

        assessed = client.patch(f"/research/opportunities/{opportunity_id}", json={
            "status": "validating", "impact_score": 5, "frequency_score": 4, "feasibility_score": 3,
        })
        assert assessed.status_code == 200
        assert assessed.json()["priority_score"] == 83
        assert len(assessed.json()["evidence"]) == 1

        blocked_validation = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert blocked_validation.status_code == 409

        second_evidence = client.post(f"/research/opportunities/{opportunity_id}/evidence", json={
            "source_type": "app_review",
            "source_url": "https://example.org/reviews/website-builder",
            "source_label": "Public app review",
            "observation_summary": "A separate user review describes difficulty maintaining a small-business website.",
            "signal_strength": "medium",
        })
        assert second_evidence.status_code == 201

        validated = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert validated.status_code == 200
        prioritized = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "prioritized"}
        )
        assert prioritized.status_code == 200
        assert prioritized.json()["status"] == "prioritized"
        assert len(prioritized.json()["evidence"]) == 2

        listed = client.get("/research/opportunities?domain_id=web")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
    finally:
        get_settings.cache_clear()


def test_research_rejects_unsafe_urls_duplicate_evidence_and_invalid_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-validation.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "content", "title": "Content planning",
            "problem_statement": "People struggle to plan consistent content.", "audience": "Creators",
        })
        opportunity_id = created.json()["opportunity_id"]
        payload = {
            "source_type": "app_review", "source_url": "http://127.0.0.1/private",
            "source_label": "Unsafe source", "observation_summary": "Not accepted.",
        }
        assert client.post(f"/research/opportunities/{opportunity_id}/evidence", json=payload).status_code == 422
        payload["source_url"] = "https://example.com/review/1"
        assert client.post(f"/research/opportunities/{opportunity_id}/evidence", json=payload).status_code == 201
        assert client.post(f"/research/opportunities/{opportunity_id}/evidence", json=payload).status_code == 409
        invalid = client.patch(f"/research/opportunities/{opportunity_id}", json={"status": "validated"})
        assert invalid.status_code == 409
    finally:
        get_settings.cache_clear()


def test_platform_and_research_routes_require_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-auth.sqlite3"))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/platform/domains").status_code in (401, 403)
        assert client.get("/research/opportunities").status_code in (401, 403)
    finally:
        get_settings.cache_clear()


def test_consent_feedback_lifecycle_and_deletion(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-feedback.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        payload = {
            "domain_id": "productivity",
            "audience_segment": "Independent creators",
            "need_summary": "Creators need one place to plan and review content work.",
            "current_workaround": "They switch between several unrelated tools.",
            "impact_score": 4,
            "frequency_score": 5,
        }
        missing_consent = client.post("/research/feedback", json=payload)
        assert missing_consent.status_code == 422

        identifying_text = client.post(
            "/research/feedback",
            json={
                **payload,
                "need_summary": "Please contact user@example.com about this request.",
                "consent_to_research": True,
            },
        )
        assert identifying_text.status_code == 422

        created = client.post(
            "/research/feedback", json={**payload, "consent_to_research": True}
        )
        assert created.status_code == 201
        feedback = created.json()
        assert feedback["status"] == "new"
        assert feedback["consent_version"] == "research-feedback-v1"
        assert "email" not in feedback
        assert "contact" not in feedback

        listed = client.get("/research/feedback/entries?domain_id=productivity")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        reviewed = client.patch(
            f"/research/feedback/{feedback['feedback_id']}", json={"status": "reviewed"}
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "reviewed"

        deleted = client.delete(f"/research/feedback/{feedback['feedback_id']}")
        assert deleted.status_code == 204
        assert client.get("/research/feedback/entries").json()["count"] == 0
    finally:
        get_settings.cache_clear()


def test_outcome_measurements_are_owner_scoped_and_time_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-outcomes.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "automation",
            "title": "Reduce repetitive admin work",
            "problem_statement": "Independent workers spend time on repetitive follow-ups.",
            "audience": "Independent workers",
        })
        assert created.status_code == 201
        opportunity_id = created.json()["opportunity_id"]

        invalid_period = client.post(
            f"/research/opportunities/{opportunity_id}/outcomes",
            json={
                "metric_name": "task_time_saved_minutes",
                "baseline_value": 20,
                "observed_value": 12,
                "unit": "minutes",
                "sample_size": 8,
                "period_start": "2026-11-15T00:00:00+00:00",
                "period_end": "2026-11-14T00:00:00+00:00",
            },
        )
        assert invalid_period.status_code == 422

        naive_period = client.post(
            f"/research/opportunities/{opportunity_id}/outcomes",
            json={
                "metric_name": "task_time_saved_minutes",
                "baseline_value": 20,
                "observed_value": 12,
                "unit": "minutes",
                "sample_size": 8,
                "period_start": "2026-11-01T00:00:00",
                "period_end": "2026-11-14T00:00:00",
            },
        )
        assert naive_period.status_code == 422

        measured = client.post(
            f"/research/opportunities/{opportunity_id}/outcomes",
            json={
                "metric_name": "task_time_saved_minutes",
                "baseline_value": 20,
                "observed_value": 12,
                "unit": "minutes",
                "sample_size": 8,
                "period_start": "2026-11-01T00:00:00+00:00",
                "period_end": "2026-11-14T00:00:00+00:00",
                "notes": "Small pilot; results are directional only.",
            },
        )
        assert measured.status_code == 201
        assert measured.json()["baseline_value"] == 20
        assert measured.json()["observed_value"] == 12
        listed = client.get(f"/research/opportunities/{opportunity_id}/outcomes")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
    finally:
        get_settings.cache_clear()


def test_public_discovery_returns_review_only_hacker_news_candidates(tmp_path, monkeypatch):
    from mrhub.research import discovery

    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-discovery-hn.sqlite3"))
    monkeypatch.setattr(discovery, "_bounded_json", lambda _url, _params: {
        "hits": [{
            "objectID": "123456",
            "title": "How do you manage repetitive admin work?",
            "created_at": "2026-11-14T10:00:00Z",
            "points": 42,
            "num_comments": 18,
            "author": "must-not-be-exposed",
        }]
    })
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        response = client.get(
            "/research/discovery/search",
            params={"query": "repetitive admin work", "source": "hacker_news", "limit": 5},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["review_required"] is True
        assert result["automatically_saved_as_evidence"] is False
        assert result["count"] == 1
        item = result["items"][0]
        assert item["source_url"] == "https://news.ycombinator.com/item?id=123456"
        assert "author" not in item
        repeated = client.get(
            "/research/discovery/search",
            params={"query": "repetitive admin work", "source": "hacker_news", "limit": 5},
        )
        assert repeated.status_code == 429
    finally:
        get_settings.cache_clear()


def test_public_discovery_only_returns_expected_stack_exchange_hosts(tmp_path, monkeypatch):
    from mrhub.research import discovery

    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-discovery-se.sqlite3"))
    monkeypatch.setattr(discovery, "_bounded_json", lambda _url, _params: {
        "items": [
            {
                "title": "A relevant public question",
                "link": "https://superuser.com/questions/123/example",
                "creation_date": 1794650400,
                "score": 9,
                "answer_count": 2,
                "tags": ["workflow", "automation"],
            },
            {
                "title": "Unexpected host must be filtered",
                "link": "https://example.org/questions/456",
                "creation_date": 1794650400,
            },
        ]
    })
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        response = client.get(
            "/research/discovery/search",
            params={"query": "workflow automation", "source": "stack_exchange", "site": "superuser"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["source_url"].startswith("https://superuser.com/")
        assert items[0]["tags"] == ["workflow", "automation"]
    finally:
        get_settings.cache_clear()



def test_discovery_rate_limit_is_shared_across_limiter_instances(tmp_path):
    from mrhub.infrastructure.database import TaskRepository
    from mrhub.research.discovery import _DiscoveryLimiter, ResearchDiscoveryError

    database_path = tmp_path / "shared-discovery-limit.sqlite3"
    TaskRepository(database_path).initialize()

    first_worker = _DiscoveryLimiter()
    second_worker = _DiscoveryLimiter()
    first_worker.check(database_path, "owner-a", "hacker_news:automation")
    try:
        second_worker.check(database_path, "owner-a", "hacker_news:automation")
    except ResearchDiscoveryError as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("A second worker must observe the shared query cooldown")

    # Limits are owner-scoped; another authenticated owner has an independent budget.
    second_worker.check(database_path, "owner-b", "hacker_news:automation")


def test_discovery_provider_backoff_is_shared_across_owners(tmp_path):
    from mrhub.infrastructure.database import TaskRepository
    from mrhub.research.discovery import _DiscoveryLimiter, ResearchDiscoveryError

    database_path = tmp_path / "provider-backoff.sqlite3"
    TaskRepository(database_path).initialize()
    limiter = _DiscoveryLimiter()
    limiter.set_provider_backoff(database_path, "stack_exchange", 30)

    for owner_id in ("owner-a", "owner-b"):
        try:
            limiter.check(
                database_path, owner_id, "stack_exchange:superuser:help", "stack_exchange"
            )
        except ResearchDiscoveryError as exc:
            assert exc.status_code == 429
            assert exc.retry_after_seconds is not None
            assert 1 <= exc.retry_after_seconds <= 30
        else:
            raise AssertionError("Provider cooldown must apply across all owners")
