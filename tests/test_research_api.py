from datetime import UTC, datetime, timedelta

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

        published_at = datetime.now(UTC).isoformat()
        evidence = client.post(f"/research/opportunities/{opportunity_id}/evidence", json={
            "source_type": "public_discussion",
            "source_url": "https://example.com/community/thread-1",
            "source_label": "Public community thread",
            "observation_summary": "Several participants describe website setup as confusing and expensive.",
            "signal_strength": "high",
            "publisher_group": "Example Research Network",
            "published_at": published_at,
            "independence_basis": "A public discussion hosted by an independently operated community; ownership checked separately.",
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

        same_host_evidence = client.post(
            f"/research/opportunities/{opportunity_id}/evidence",
            json={
                "source_type": "app_review",
                "source_url": "https://example.com/reviews/another-page",
                "source_label": "Another source type on the same host",
                "observation_summary": "This is a distinct URL but not a distinct host.",
                "signal_strength": "medium",
                "publisher_group": "Example Research Network",
                "published_at": published_at,
                "independence_basis": "A review platform with distinct editorial ownership, checked separately.",
            },
        )
        assert same_host_evidence.status_code == 201
        same_host_validation = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert same_host_validation.status_code == 409

        second_evidence = client.post(f"/research/opportunities/{opportunity_id}/evidence", json={
            "source_type": "app_review",
            "source_url": "https://example.org/reviews/website-builder",
            "source_label": "Public app review",
            "observation_summary": "A separate user review describes difficulty maintaining a small-business website.",
            "signal_strength": "medium",
            "publisher_group": "Independent App Reviews",
            "published_at": published_at,
            "independence_basis": "A separate app-review publisher; editorial ownership and publication origin checked.",
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
        assert len(prioritized.json()["evidence"]) == 3

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
    from mrhub.research.discovery import ResearchDiscoveryError, _DiscoveryLimiter

    database_path = tmp_path / "shared-discovery-limit.sqlite3"
    TaskRepository(database_path).initialize()

    first_worker = _DiscoveryLimiter()
    second_worker = _DiscoveryLimiter()
    first_worker.check(database_path, "owner-a", "hacker_news:automation", "hacker_news")
    try:
        second_worker.check(database_path, "owner-a", "hacker_news:automation", "hacker_news")
    except ResearchDiscoveryError as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("A second worker must observe the shared query cooldown")

    # Limits are owner-scoped; another authenticated owner has an independent budget.
    second_worker.check(database_path, "owner-b", "hacker_news:automation", "hacker_news")


def test_discovery_provider_backoff_is_shared_across_owners(tmp_path):
    from mrhub.infrastructure.database import TaskRepository
    from mrhub.research.discovery import ResearchDiscoveryError, _DiscoveryLimiter

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


def test_research_source_provenance_is_deduplicated_across_opportunities(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-source-registry.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        first = client.post("/research/opportunities", json={
            "domain_id": "web",
            "title": "Website onboarding",
            "problem_statement": "New owners struggle to launch a site.",
            "audience": "Small business owners",
        }).json()
        second = client.post("/research/opportunities", json={
            "domain_id": "content",
            "title": "Content onboarding",
            "problem_statement": "Creators struggle to publish consistently.",
            "audience": "Independent creators",
        }).json()
        third = client.post("/research/opportunities", json={
            "domain_id": "automation",
            "title": "Workflow onboarding",
            "problem_statement": "People struggle to coordinate repetitive work.",
            "audience": "Independent workers",
        }).json()
        published_at = datetime.now(UTC).isoformat()
        common = {
            "source_type": "public_discussion",
            "source_label": "Example public discussion",
            "observation_summary": "The source describes a recurring workflow problem.",
            "signal_strength": "medium",
            "publisher_group": "Example Media Group",
            "published_at": published_at,
        }
        first_evidence = client.post(
            f"/research/opportunities/{first['opportunity_id']}/evidence",
            json={**common, "source_url": "https://Example.com/research/thread/"},
        )
        second_evidence = client.post(
            f"/research/opportunities/{second['opportunity_id']}/evidence",
            json={**common, "source_url": "https://example.com/research/thread"},
        )

        assert first_evidence.status_code == 201
        assert second_evidence.status_code == 201
        first_item = first_evidence.json()
        second_item = second_evidence.json()
        assert first_item["canonical_url"] == "https://example.com/research/thread"
        assert first_item["source_id"] == second_item["source_id"]
        assert first_item["hostname"] == "example.com"
        assert first_item["publisher_group"] == "Example Media Group"
        assert first_item["source_usage_count"] == 1
        assert second_item["source_usage_count"] == 2
        first_details = client.get(
            f"/research/opportunities/{first['opportunity_id']}"
        ).json()["evidence"][0]
        assert first_details["source_usage_count"] == 2
        assert first_item["source_first_captured_at"] == second_item["source_first_captured_at"]
        assert first_details["source_last_captured_at"] == second_item["source_last_captured_at"]
        assert first_item["freshness_status"] == "current"
        assert first_item["age_days"] == 0

        conflicting_group = client.post(
            f"/research/opportunities/{third['opportunity_id']}/evidence",
            json={
                **common,
                "publisher_group": "Different Publisher",
                "source_url": "https://example.com/research/thread",
            },
        )
        assert conflicting_group.status_code == 409
    finally:
        get_settings.cache_clear()


def test_research_published_at_requires_timezone_and_rejects_future_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-freshness.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "learning",
            "title": "Learning support",
            "problem_statement": "Learners need clearer study workflows.",
            "audience": "Independent learners",
        }).json()
        opportunity_id = created["opportunity_id"]
        payload = {
            "source_type": "research_report",
            "source_url": "https://research.example.org/reports/learning",
            "source_label": "Learning report",
            "observation_summary": "The report describes a measurable learning barrier.",
            "publisher_group": "Learning Research Institute",
        }

        naive = client.post(
            f"/research/opportunities/{opportunity_id}/evidence",
            json={**payload, "published_at": "2026-11-01T12:00:00"},
        )
        assert naive.status_code == 422

        future = client.post(
            f"/research/opportunities/{opportunity_id}/evidence",
            json={
                **payload,
                "source_url": "https://research.example.org/reports/future",
                "published_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
        assert future.status_code == 422

        stale = client.post(
            f"/research/opportunities/{opportunity_id}/evidence",
            json={
                **payload,
                "source_url": "https://research.example.org/reports/old",
                "published_at": (datetime.now(UTC) - timedelta(days=731)).isoformat(),
            },
        )
        assert stale.status_code == 201
        assert stale.json()["freshness_status"] == "stale"
        assert stale.json()["age_days"] >= 731
    finally:
        get_settings.cache_clear()


def test_research_validation_requires_fresh_sources_and_distinct_publisher_groups(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-validation-quality.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "automation",
            "title": "Reduce repetitive administration",
            "problem_statement": "Independent workers repeat the same administrative tasks.",
            "audience": "Independent workers",
        }).json()
        opportunity_id = created["opportunity_id"]
        assert client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validating"}
        ).status_code == 200
        published_at = datetime.now(UTC).isoformat()

        first = {
            "source_type": "public_discussion",
            "source_url": "https://forum.example.com/thread/1",
            "source_label": "Public discussion",
            "observation_summary": "People describe the repeated task.",
            "publisher_group": "Shared Media Group",
            "published_at": published_at,
            "independence_basis": "Public forum ownership and publication origin reviewed.",
        }
        second = {
            "source_type": "app_review",
            "source_url": "https://reviews.example.org/item/1",
            "source_label": "App review",
            "observation_summary": "Users report the same workflow friction.",
            "publisher_group": "Shared Media Group",
            "published_at": published_at,
            "independence_basis": "App-review publisher ownership and publication origin reviewed.",
        }
        assert client.post(
            f"/research/opportunities/{opportunity_id}/evidence", json=first
        ).status_code == 201
        assert client.post(
            f"/research/opportunities/{opportunity_id}/evidence", json=second
        ).status_code == 201

        same_publisher = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert same_publisher.status_code == 409

        stale = {
            "source_type": "research_report",
            "source_url": "https://archive.example.net/report/old",
            "source_label": "Older research report",
            "observation_summary": "This source is outside its freshness window.",
            "publisher_group": "Independent Research Archive",
            "published_at": (datetime.now(UTC) - timedelta(days=731)).isoformat(),
        }
        stale_response = client.post(
            f"/research/opportunities/{opportunity_id}/evidence", json=stale
        )
        assert stale_response.status_code == 201
        assert stale_response.json()["freshness_status"] == "stale"
        stale_only = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert stale_only.status_code == 409

        fresh_independent = client.post(
            f"/research/opportunities/{opportunity_id}/evidence",
            json={
                "source_type": "research_report",
                "source_url": "https://independent.example.net/report/current",
                "source_label": "Current independent report",
                "observation_summary": "A current independent report corroborates the problem.",
                "publisher_group": "Independent Research Institute",
                "published_at": published_at,
                "independence_basis": "Research institute publication and editorial governance checked independently.",
            },
        )
        assert fresh_independent.status_code == 201
        validated = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert validated.status_code == 200
        assert validated.json()["status"] == "validated"
    finally:
        get_settings.cache_clear()


def test_research_validation_still_requires_distinct_hostnames(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-host-diversity.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "business_ops",
            "title": "Operations coordination",
            "problem_statement": "Small teams struggle to coordinate routine work.",
            "audience": "Small teams",
        }).json()
        opportunity_id = created["opportunity_id"]
        published_at = datetime.now(UTC).isoformat()

        for source_type, path_part, publisher_group in (
            ("public_discussion", "discussion", "Publisher One"),
            ("app_review", "review", "Publisher Two"),
        ):
            response = client.post(
                f"/research/opportunities/{opportunity_id}/evidence",
                json={
                    "source_type": source_type,
                    "source_url": f"https://same.example.com/{path_part}/item",
                    "source_label": publisher_group,
                    "observation_summary": "The source describes the same operational problem.",
                    "publisher_group": publisher_group,
                    "published_at": published_at,
                },
            )
            assert response.status_code == 201

        assert client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validating"}
        ).status_code == 200
        blocked = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert blocked.status_code == 409
    finally:
        get_settings.cache_clear()


def test_research_source_default_publisher_group_accepts_long_valid_hostnames(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-long-host.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "web",
            "title": "Long host provenance",
            "problem_statement": "A source can use a long but valid public hostname.",
            "audience": "Website operators",
        }).json()
        hostname = ".".join(("a" * 60, "b" * 60, "c" * 60, "example"))
        response = client.post(
            f"/research/opportunities/{created['opportunity_id']}/evidence",
            json={
                "source_type": "other",
                "source_url": f"https://{hostname}/source",
                "source_label": "Long-host source",
                "observation_summary": "The source uses a valid long hostname.",
            },
        )
        assert response.status_code == 201
        assert response.json()["hostname"] == hostname
        assert response.json()["publisher_group"] == hostname
    finally:
        get_settings.cache_clear()


def test_research_validation_requires_recorded_independence_rationale(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-independence.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "web",
            "title": "Independent source review",
            "problem_statement": "Small teams struggle to validate customer needs.",
            "audience": "Small teams",
        }).json()
        opportunity_id = created["opportunity_id"]
        published_at = datetime.now(UTC).isoformat()
        evidence_ids = []
        for host, group, source_type in (
            ("one.example", "Publisher One", "public_discussion"),
            ("two.example", "Publisher Two", "app_review"),
        ):
            response = client.post(
                f"/research/opportunities/{opportunity_id}/evidence",
                json={
                    "source_type": source_type,
                    "source_url": f"https://{host}/discussion",
                    "source_label": "Public source",
                    "observation_summary": "The source reports a recurring workflow problem.",
                    "signal_strength": "medium",
                    "published_at": published_at,
                    "publisher_group": group,
                },
            )
            assert response.status_code == 201
            evidence_ids.append(response.json()["evidence_id"])

        blank_review = client.patch(
            f"/research/opportunities/{opportunity_id}/evidence/{evidence_ids[0]}/independence",
            json={"independence_basis": "   "},
        )
        assert blank_review.status_code == 422

        blocked = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert blocked.status_code == 409

        for evidence_id in evidence_ids:
            reviewed = client.patch(
                f"/research/opportunities/{opportunity_id}/evidence/{evidence_id}/independence",
                json={
                    "independence_basis": "Ownership and editorial origin reviewed against the other source."
                },
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["independence_basis"]

        validated = client.patch(
            f"/research/opportunities/{opportunity_id}", json={"status": "validated"}
        )
        assert validated.status_code == 200
    finally:
        get_settings.cache_clear()
