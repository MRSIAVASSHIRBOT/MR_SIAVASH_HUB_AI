"""Focused safety tests for video-generation worker ambiguity handling."""

from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationResult,
    VideoGenerationSubmission,
)
from mrhub.video_intelligence.generation_worker import VideoGenerationWorkerHandler


class RecordingJobs:
    def __init__(self, loaded=None):
        self.loaded = loaded
        self.transitions = []

    def load_for_worker(self, _task_id):
        return self.loaded

    def get(self, _owner, _generation_id):
        return None

    def transition_under_lease(self, owner, generation_id, status, **kwargs):
        self.transitions.append((owner, generation_id, status, kwargs))


class LookupOnlyProvider:
    capability = SimpleNamespace(provider="fixture", model="fixture-v1", local=True)

    def __init__(self, *, lookup_result=None, lookup_error=None, status_result=None):
        self.lookup_result = lookup_result
        self.lookup_error = lookup_error
        self.status_result = status_result
        self.cancel_result = False
        self.cancel_error = None
        self.cancel_calls = 0
        self.submit_calls = 0
        self.lookup_calls = 0
        self.status_calls = 0

    def submit(self, _request):
        self.submit_calls += 1
        raise AssertionError("Reconciliation must never submit or replay work")

    def find_by_idempotency_key(self, _key):
        self.lookup_calls += 1
        if self.lookup_error:
            raise self.lookup_error
        return self.lookup_result

    def get_status(self, _provider_job_id):
        self.status_calls += 1
        if isinstance(self.status_result, Exception):
            raise self.status_result
        return self.status_result

    def cancel(self, _provider_job_id):
        self.cancel_calls += 1
        if self.cancel_error is not None:
            raise self.cancel_error
        return self.cancel_result


def _handler():
    handler = object.__new__(VideoGenerationWorkerHandler)
    handler.jobs = RecordingJobs()
    return handler


def test_reconciliation_lookup_miss_keeps_unknown_outcome_without_replay():
    handler = _handler()
    provider = LookupOnlyProvider()
    generation_id = uuid4()

    result = handler._reconcile(
        provider,
        "fixture",
        "fixture-v1",
        "owner-1",
        generation_id,
        None,
        object(),
        Event(),
    )

    assert result == {
        "generation_id": str(generation_id),
        "status": "unknown_outcome",
        "reason_code": "provider_submission_not_discoverable",
    }
    assert provider.lookup_calls == 1
    assert provider.submit_calls == 0
    assert provider.status_calls == 0
    assert handler.jobs.transitions == []


def test_reconciliation_lookup_failure_remains_ambiguous_without_replay():
    handler = _handler()
    provider = LookupOnlyProvider(lookup_error=TimeoutError("private provider detail"))

    with pytest.raises(ValueError, match="provider_reconciliation_lookup_failed"):
        handler._reconcile(
            provider,
            "fixture",
            "fixture-v1",
            "owner-1",
            uuid4(),
            None,
            object(),
            Event(),
        )

    assert provider.submit_calls == 0
    assert provider.status_calls == 0
    assert handler.jobs.transitions == []


def test_reconciliation_uses_discovered_job_reference_and_only_polls_status():
    handler = _handler()
    generation_id = uuid4()
    submission = VideoGenerationSubmission(
        provider="fixture",
        model="fixture-v1",
        provider_job_id="opaque-job-42",
        status=GenerationStatus.ACCEPTED,
        progress_percent=12,
    )
    status = VideoGenerationResult(
        provider="fixture",
        model="fixture-v1",
        provider_job_id="opaque-job-42",
        status=GenerationStatus.RUNNING,
    )
    provider = LookupOnlyProvider(lookup_result=submission, status_result=status)

    result = handler._reconcile(
        provider,
        "fixture",
        "fixture-v1",
        "owner-1",
        generation_id,
        None,
        object(),
        Event(),
    )

    assert result == {"generation_id": str(generation_id), "status": "running"}
    assert provider.lookup_calls == 1
    assert provider.status_calls == 1
    assert provider.submit_calls == 0
    assert [item[2] for item in handler.jobs.transitions] == ["running", "running"]
    assert handler.jobs.transitions[0][3]["provider_job_id"] == "opaque-job-42"


def test_reconciliation_rejects_provider_identity_mismatch_without_poll_or_replay():
    handler = _handler()
    provider = LookupOnlyProvider(
        lookup_result=VideoGenerationSubmission(
            provider="unexpected",
            model="fixture-v1",
            provider_job_id="opaque-job-42",
            status=GenerationStatus.ACCEPTED,
        )
    )

    with pytest.raises(ValueError, match="provider_reconciliation_identity_mismatch"):
        handler._reconcile(
            provider,
            "fixture",
            "fixture-v1",
            "owner-1",
            uuid4(),
            None,
            object(),
            Event(),
        )

    assert provider.status_calls == 0
    assert provider.submit_calls == 0
    assert handler.jobs.transitions == []


def test_submit_exception_is_persisted_as_unknown_outcome_not_retried():
    handler = _handler()
    generation_id = uuid4()

    class AmbiguousSubmitProvider:
        def __init__(self):
            self.submit_calls = 0

        def submit(self, _request):
            self.submit_calls += 1
            raise TimeoutError("provider may have accepted the request")

    provider = AmbiguousSubmitProvider()

    with pytest.raises(ValueError, match="provider_submission_outcome_unknown"):
        handler._submit_once(
            provider,
            SimpleNamespace(),
            "fixture",
            "fixture-v1",
            "owner-1",
            generation_id,
            object(),
            Event(),
        )

    assert provider.submit_calls == 1
    assert [item[2] for item in handler.jobs.transitions] == [
        "submitting",
        "unknown_outcome",
    ]
    assert handler.jobs.transitions[-1][3]["error_code"] == (
        "provider_submission_outcome_unknown"
    )



def test_stale_submitting_job_is_reconciled_by_lookup_without_replay(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module

    generation_id = uuid4()
    handler = _handler()
    handler.jobs.loaded = {
        "owner_user_id": "owner-1",
        "generation_id": str(generation_id),
        "provider": "fixture",
        "model": "fixture-v1",
        "status": "submitting",
        "provider_job_id": None,
    }
    submission = VideoGenerationSubmission(
        provider="fixture",
        model="fixture-v1",
        provider_job_id="opaque-job-lease-recovery",
        status=GenerationStatus.ACCEPTED,
        progress_percent=15,
    )
    status = VideoGenerationResult(
        provider="fixture",
        model="fixture-v1",
        provider_job_id="opaque-job-lease-recovery",
        status=GenerationStatus.RUNNING,
    )
    provider = LookupOnlyProvider(lookup_result=submission, status_result=status)
    monkeypatch.setattr(
        registry_module.video_generation_registry,
        "get",
        lambda _provider, _model: provider,
    )

    result = handler(
        SimpleNamespace(task_id=uuid4()),
        lease=object(),
        lease_lost=Event(),
    )

    assert result == {"generation_id": str(generation_id), "status": "running"}
    assert provider.lookup_calls == 1
    assert provider.status_calls == 1
    assert provider.submit_calls == 0
    assert [item[2] for item in handler.jobs.transitions] == ["running", "running"]


def test_stale_submitting_lookup_miss_is_marked_ambiguous(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module

    generation_id = uuid4()
    handler = _handler()
    handler.jobs.loaded = {
        "owner_user_id": "owner-1",
        "generation_id": str(generation_id),
        "provider": "fixture",
        "model": "fixture-v1",
        "status": "submitting",
        "provider_job_id": None,
    }
    provider = LookupOnlyProvider()
    monkeypatch.setattr(
        registry_module.video_generation_registry,
        "get",
        lambda _provider, _model: provider,
    )

    result = handler(
        SimpleNamespace(task_id=uuid4()),
        lease=object(),
        lease_lost=Event(),
    )

    assert result == {
        "generation_id": str(generation_id),
        "status": "unknown_outcome",
        "reason_code": "provider_submission_not_discoverable",
    }
    assert provider.lookup_calls == 1
    assert provider.submit_calls == 0
    assert [item[2] for item in handler.jobs.transitions] == ["unknown_outcome"]
    assert handler.jobs.transitions[0][3]["error_code"] == (
        "provider_submission_not_discoverable"
    )



def test_provider_cancellation_is_confirmed_by_status_before_marking_cancelled():
    handler = _handler()
    generation_id = uuid4()
    provider = LookupOnlyProvider(
        status_result=VideoGenerationResult(
            provider="fixture",
            model="fixture-v1",
            provider_job_id="provider-cancel-1",
            status=GenerationStatus.CANCELLED,
        )
    )
    provider.cancel_result = True

    result = handler._reconcile(
        provider, "fixture", "fixture-v1", "owner-1", generation_id,
        "provider-cancel-1", object(), Event(),
        initial_status="running", cancellation_requested=True,
    )

    assert result == {"generation_id": str(generation_id), "status": "cancelled"}
    assert provider.cancel_calls == 1
    assert provider.status_calls == 1
    assert provider.submit_calls == 0
    assert [item[2] for item in handler.jobs.transitions] == ["cancelled"]


def test_provider_cancellation_request_keeps_running_job_active_until_confirmed():
    handler = _handler()
    generation_id = uuid4()
    provider = LookupOnlyProvider(
        status_result=VideoGenerationResult(
            provider="fixture",
            model="fixture-v1",
            provider_job_id="provider-cancel-2",
            status=GenerationStatus.RUNNING,
        )
    )
    provider.cancel_result = True

    result = handler._reconcile(
        provider, "fixture", "fixture-v1", "owner-1", generation_id,
        "provider-cancel-2", object(), Event(),
        initial_status="running", cancellation_requested=True,
    )

    assert result["status"] == "running"
    assert result["cancellation_requested"] is True
    assert result["reason_code"] == "provider_cancellation_pending"
    assert provider.cancel_calls == 1
    assert provider.status_calls == 1
    assert [item[2] for item in handler.jobs.transitions] == ["running"]


def test_provider_cancellation_failure_is_sanitized_and_does_not_fake_success():
    handler = _handler()
    generation_id = uuid4()
    provider = LookupOnlyProvider(
        status_result=VideoGenerationResult(
            provider="fixture",
            model="fixture-v1",
            provider_job_id="provider-cancel-3",
            status=GenerationStatus.RUNNING,
        )
    )
    provider.cancel_error = RuntimeError("private provider token and URL")

    result = handler._reconcile(
        provider, "fixture", "fixture-v1", "owner-1", generation_id,
        "provider-cancel-3", object(), Event(),
        initial_status="running", cancellation_requested=True,
    )

    assert result["status"] == "running"
    assert result["cancellation_requested"] is True
    assert result["reason_code"] == "provider_cancellation_failed"
    assert "private provider token" not in str(result)
    assert provider.cancel_calls == 1
    assert provider.status_calls == 1
    assert [item[2] for item in handler.jobs.transitions] == ["running"]


def test_ambiguous_submission_cancellation_only_looks_up_original_job_key():
    handler = _handler()
    generation_id = uuid4()
    provider = LookupOnlyProvider()

    result = handler._reconcile(
        provider, "fixture", "fixture-v1", "owner-1", generation_id,
        None, object(), Event(),
        initial_status="unknown_outcome", cancellation_requested=True,
    )

    assert result["status"] == "unknown_outcome"
    assert result["cancellation_requested"] is True
    assert provider.lookup_calls == 1
    assert provider.cancel_calls == 0
    assert provider.submit_calls == 0
    assert provider.status_calls == 0


def test_worker_observes_a_cancellation_requested_during_provider_submission(
    monkeypatch,
):
    from mrhub.video_intelligence import generation_registry as registry_module

    generation_id = uuid4()
    handler = _handler()
    loaded = {
        "owner_user_id": "owner-1",
        "generation_id": str(generation_id),
        "provider": "fixture",
        "model": "fixture-v1",
        "status": "queued",
        "provider_job_id": None,
        "request": {
            "prompt": "original",
            "aspect_ratio": "9:16",
            "duration_seconds": 10,
            "resolution": "720p",
        },
        "cancellation_requested": False,
    }

    class CancellingJobs(RecordingJobs):
        def __init__(self, initial):
            super().__init__(initial)
            self.get_calls = 0

        def get(self, _owner, _generation_id):
            self.get_calls += 1
            if self.get_calls == 1:
                return None
            return {"cancellation_requested_at": "2026-11-17T00:00:00+00:00"}

    handler.jobs = CancellingJobs(loaded)

    class AcceptedThenCancelledProvider(LookupOnlyProvider):
        capability = SimpleNamespace(
            provider="fixture",
            local=True,
            model="fixture-v1",
            max_duration_seconds=30,
            max_resolution="720p",
            supported_aspect_ratios=("9:16",),
        )

        def submit(self, _request):
            return VideoGenerationSubmission(
                provider="fixture",
                model="fixture-v1",
                provider_job_id="provider-after-submit",
                status=GenerationStatus.ACCEPTED,
            )

    provider = AcceptedThenCancelledProvider(
        status_result=VideoGenerationResult(
            provider="fixture",
            model="fixture-v1",
            provider_job_id="provider-after-submit",
            status=GenerationStatus.CANCELLED,
        )
    )
    provider.cancel_result = True
    monkeypatch.setattr(
        registry_module.video_generation_registry,
        "get",
        lambda _provider, _model: provider,
    )

    result = handler(
        SimpleNamespace(task_id=uuid4()),
        lease=object(),
        lease_lost=Event(),
    )

    assert result["status"] == "cancelled"
    assert provider.cancel_calls == 1
    assert provider.status_calls == 1


def test_queued_cancellation_is_completed_without_provider_lookup(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module

    generation_id = uuid4()
    handler = _handler()
    handler.jobs.loaded = {
        "owner_user_id": "owner-1",
        "generation_id": str(generation_id),
        "provider": "fixture",
        "model": "fixture-v1",
        "status": "queued",
        "provider_job_id": None,
        "request": {"prompt": "original"},
        "cancellation_requested": True,
    }
    monkeypatch.setattr(
        registry_module.video_generation_registry,
        "get",
        lambda *_args: pytest.fail("cancelled queued work must not resolve a provider"),
    )

    result = handler(
        SimpleNamespace(task_id=uuid4()),
        lease=object(),
        lease_lost=Event(),
    )

    assert result["status"] == "cancelled"
    assert [item[2] for item in handler.jobs.transitions] == ["cancelled"]


def test_hosted_provider_is_never_submitted_without_both_consents(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module
    from mrhub.video_intelligence.generation import VideoGenerationCapability

    generation_id = uuid4()
    handler = _handler()
    handler.jobs.loaded = {
        "owner_user_id": "owner-1",
        "generation_id": str(generation_id),
        "provider": "hosted-fixture",
        "model": "hosted-v1",
        "status": "queued",
        "provider_job_id": None,
        "request": {
            "prompt": "approved test prompt",
            "aspect_ratio": "9:16",
            "duration_seconds": 10,
            "resolution": "720p",
            "remote_processing_approved": True,
            "remote_spend_approved": False,
            "max_remote_cost_usd": 1.0,
        },
        "cancellation_requested": False,
    }

    class HostedProvider(LookupOnlyProvider):
        capability = VideoGenerationCapability(
            provider="hosted-fixture",
            model="hosted-v1",
            local=False,
            supported_aspect_ratios=("9:16",),
            max_duration_seconds=30,
            max_resolution="720p",
        )

        def estimate_cost_usd(self, _request):
            return 0.25

    provider = HostedProvider()
    monkeypatch.setattr(
        registry_module.video_generation_registry,
        "get",
        lambda _provider, _model: provider,
    )

    with pytest.raises(ValueError, match="remote_consent_required"):
        handler(
            SimpleNamespace(task_id=uuid4()),
            lease=object(),
            lease_lost=Event(),
        )

    assert provider.submit_calls == 0
    assert handler.jobs.transitions[-1][2] == "failed"
    assert handler.jobs.transitions[-1][3]["error_code"] == "remote_consent_required"


def test_hosted_provider_is_never_submitted_above_the_approved_budget(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module
    from mrhub.video_intelligence.generation import VideoGenerationCapability

    generation_id = uuid4()
    handler = _handler()
    handler.jobs.loaded = {
        "owner_user_id": "owner-1",
        "generation_id": str(generation_id),
        "provider": "hosted-fixture",
        "model": "hosted-v1",
        "status": "queued",
        "provider_job_id": None,
        "request": {
            "prompt": "approved test prompt",
            "aspect_ratio": "9:16",
            "duration_seconds": 10,
            "resolution": "720p",
            "remote_processing_approved": True,
            "remote_spend_approved": True,
            "max_remote_cost_usd": 0.10,
        },
        "cancellation_requested": False,
    }

    class HostedProvider(LookupOnlyProvider):
        capability = VideoGenerationCapability(
            provider="hosted-fixture",
            model="hosted-v1",
            local=False,
            supported_aspect_ratios=("9:16",),
            max_duration_seconds=30,
            max_resolution="720p",
        )

        def estimate_cost_usd(self, _request):
            return 0.25

    provider = HostedProvider()
    monkeypatch.setattr(
        registry_module.video_generation_registry,
        "get",
        lambda _provider, _model: provider,
    )

    with pytest.raises(ValueError, match="remote_budget_exceeded"):
        handler(
            SimpleNamespace(task_id=uuid4()),
            lease=object(),
            lease_lost=Event(),
        )

    assert provider.submit_calls == 0
    assert handler.jobs.transitions[-1][2] == "failed"
    assert handler.jobs.transitions[-1][3]["error_code"] == "remote_budget_exceeded"
