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
    def __init__(self):
        self.transitions = []

    def transition_under_lease(self, owner, generation_id, status, **kwargs):
        self.transitions.append((owner, generation_id, status, kwargs))


class LookupOnlyProvider:
    capability = SimpleNamespace(provider="fixture", model="fixture-v1")

    def __init__(self, *, lookup_result=None, lookup_error=None, status_result=None):
        self.lookup_result = lookup_result
        self.lookup_error = lookup_error
        self.status_result = status_result
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
