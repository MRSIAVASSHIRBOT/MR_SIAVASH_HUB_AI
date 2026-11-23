from uuid import UUID

import pytest

from mrhub.agents.lessons import (
    LessonEvidence,
    LessonProposalError,
    build_lesson_proposal,
)

WORKFLOW_ID = UUID("12345678-1234-5678-1234-567812345678")
OUTPUT_DIGEST = "a" * 64
LESSON = "Keep dependency validation ahead of all side-effecting workflow steps."


def evidence(**overrides):
    values = {
        "workflow_id": WORKFLOW_ID,
        "workflow_status": "succeeded",
        "step_id": "verify-contract",
        "step_status": "succeeded",
        "output_digest": OUTPUT_DIGEST,
        "error_code": None,
    }
    values.update(overrides)
    return LessonEvidence(**values)


def test_lesson_proposal_is_stable_and_links_to_persisted_step_evidence():
    first = build_lesson_proposal(evidence(), category="engineering", lesson_text=LESSON)
    second = build_lesson_proposal(evidence(), category="engineering", lesson_text=LESSON)

    assert first == second
    payload = first.as_dict()
    assert payload["proposal_id"] == first.proposal_id
    assert len(first.proposal_id) == 64
    assert first.evidence_digest == OUTPUT_DIGEST
    assert "workflow://12345678-1234-5678-1234-567812345678/steps/verify-contract" in first.source_reference
    assert payload["owner_review_required"] is True
    assert payload["automatic_memory_write"] is False
    assert payload["execution_authorized"] is False
    assert payload["proposed_memory_classification"] == "procedural_candidate"
    assert payload["memory_entry_preview"]["verification_status"] == "user_authored"
    assert payload["memory_entry_preview"]["memory_type"] == "procedural"
    assert set(payload["memory_entry_preview"]) == {
        "memory_type", "category", "content", "provenance", "confidence", "verification_status"
    }
    # The current Memory API has no typed memory_type field; do not invent one.


@pytest.mark.parametrize(
    "overrides",
    [
        {"workflow_status": "failed"},
        {"workflow_status": "running"},
        {"step_status": "failed"},
        {"step_status": "unknown_outcome"},
        {"output_digest": None},
        {"output_digest": "not-a-digest"},
        {"error_code": "tool_failed"},
    ],
)
def test_lesson_proposal_requires_successful_workflow_and_digest_backed_step(overrides):
    with pytest.raises(LessonProposalError):
        build_lesson_proposal(evidence(**overrides), category="engineering", lesson_text=LESSON)


@pytest.mark.parametrize(
    ("category", "lesson"),
    [
        (" ", LESSON),
        ("engineering", "too short"),
        ("engineering", "password=hunter2; this should not be stored"),
    ],
)
def test_lesson_proposal_rejects_blank_short_or_sensitive_content(category, lesson):
    with pytest.raises(LessonProposalError):
        build_lesson_proposal(evidence(), category=category, lesson_text=lesson)


def test_lesson_text_is_bounded():
    with pytest.raises(LessonProposalError):
        build_lesson_proposal(
            evidence(),
            category="engineering",
            lesson_text="A" * 501,
        )
