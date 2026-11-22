import pytest

from mrhub.agents.evaluation import (
    CriterionStatus,
    EvaluationCriterion,
    EvaluationDecision,
    EvaluationInputError,
    evaluate_criteria,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def test_all_passed_with_evidence_is_accepted():
    report = evaluate_criteria(
        [
            EvaluationCriterion("unit-tests", "Unit tests pass", CriterionStatus.PASSED, DIGEST_A),
            EvaluationCriterion("security", "Security checks pass", CriterionStatus.PASSED, DIGEST_B),
        ]
    )

    assert report.decision is EvaluationDecision.ACCEPT
    assert report.complete
    assert report.score == 1.0
    assert report.as_dict()["passed"] == 2


def test_failed_criterion_rejects_even_when_another_is_unknown():
    report = evaluate_criteria(
        [
            EvaluationCriterion("tests", "Tests pass", CriterionStatus.FAILED, DIGEST_A),
            EvaluationCriterion("runtime", "Runtime verified", CriterionStatus.UNKNOWN),
        ]
    )

    assert report.decision is EvaluationDecision.REJECT
    assert report.failed == 1
    assert report.unknown == 1
    assert not report.complete


def test_unknown_evidence_requires_review_and_is_not_scored_as_pass():
    report = evaluate_criteria(
        [
            EvaluationCriterion("tests", "Tests pass", CriterionStatus.PASSED, DIGEST_A),
            EvaluationCriterion("runtime", "Runtime verified", CriterionStatus.UNKNOWN),
        ]
    )

    assert report.decision is EvaluationDecision.REVIEW_REQUIRED
    assert report.score == 0.5


@pytest.mark.parametrize(
    "criteria",
    [
        [],
        [
            EvaluationCriterion("same", "First", CriterionStatus.PASSED, DIGEST_A),
            EvaluationCriterion("same", "Second", CriterionStatus.PASSED, DIGEST_B),
        ],
        [EvaluationCriterion("missing-evidence", "Must prove pass", CriterionStatus.PASSED)],
        [
            EvaluationCriterion(
                "bad-digest", "Digest must be valid", CriterionStatus.FAILED, "not-a-digest"
            )
        ],
        [
            EvaluationCriterion(
                "unknown-with-proof", "Unknown has no proof", CriterionStatus.UNKNOWN, DIGEST_A
            )
        ],
        [EvaluationCriterion(" ", "Invalid identifier", CriterionStatus.UNKNOWN)],
        [EvaluationCriterion("missing-description", " ", CriterionStatus.UNKNOWN)],
    ],
)
def test_invalid_evaluation_inputs_are_rejected(criteria):
    with pytest.raises(EvaluationInputError):
        evaluate_criteria(criteria)


def test_criteria_limit_is_enforced():
    criteria = [
        EvaluationCriterion(f"criterion-{index}", "Description", CriterionStatus.UNKNOWN)
        for index in range(101)
    ]
    with pytest.raises(EvaluationInputError, match="At most"):
        evaluate_criteria(criteria)


def test_criteria_limit_stops_consuming_large_iterables():
    consumed = 0

    def criteria_stream():
        nonlocal consumed
        for index in range(1_000):
            consumed += 1
            yield EvaluationCriterion(
                f"criterion-{index}", "Description", CriterionStatus.UNKNOWN
            )

    with pytest.raises(EvaluationInputError, match="At most"):
        evaluate_criteria(criteria_stream())

    assert consumed == 101
