from uuid import uuid4

import pytest

from mrhub.agents.core import AgentPlanRequest
from mrhub.agents.evaluation import (
    CriterionStatus,
    EvaluationCriterion,
    EvaluationDecision,
    EvaluationInputError,
    evaluate_criteria,
)
from mrhub.agents.workflow_runner import AgentWorkflowRunner


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


def test_failed_tool_digest_is_bound_to_its_persisted_workflow_checkpoint():
    class StoredFailure:
        def get_run(self, workflow_id, *, owner_user_id):
            return {
                "steps": [
                    {
                        "step_number": 2,
                        "status": "failed",
                        "error_code": "tool_execution_failed",
                        "attempt_count": 2,
                        "started_at": "2026-11-22T10:00:00+00:00",
                        "finished_at": "2026-11-22T10:00:01+00:00",
                    }
                ]
            }

    class StoredCore:
        def ordered_tool_steps(self, request, _plan):
            return [(2, 2, request.tools[0])]

    runner = object.__new__(AgentWorkflowRunner)
    runner.recovery = StoredFailure()
    runner.core = StoredCore()
    request = AgentPlanRequest(
        goal="Evaluate a persisted failed tool step",
        tools=[{"name": "text.echo", "payload": {"text": "example"}}],
    )

    plan = {
        "dependency_plan": {
            "ordered_steps": [
                {
                    "step_id": "step-1",
                    "description": "Select the model provider",
                    "depends_on": [],
                },
                {
                    "step_id": "step-2",
                    "description": "Execute the requested tool",
                    "depends_on": ["step-1"],
                },
            ]
        }
    }
    first = runner._evaluate_workflow_tools(
        uuid4(), request, plan=plan, owner_user_id="owner"
    )
    second = runner._evaluate_workflow_tools(
        uuid4(), request, plan=plan, owner_user_id="owner"
    )

    assert first is not None and second is not None
    first_digest = first["criteria"][0]["evidence_digest"]
    second_digest = second["criteria"][0]["evidence_digest"]
    assert first["decision"] == "reject"
    assert len(first_digest) == 64
    assert first_digest != second_digest


def test_evaluation_follows_topological_execution_order_not_request_array_order():
    class StoredRun:
        def get_run(self, workflow_id, *, owner_user_id):
            return {
                "steps": [
                    {
                        "step_number": 2,
                        "status": "succeeded",
                        "output_digest": DIGEST_A,
                    },
                    {
                        "step_number": 3,
                        "status": "failed",
                        "error_code": "tool_execution_failed",
                        "attempt_count": 1,
                        "started_at": "2026-11-22T10:00:00+00:00",
                        "finished_at": "2026-11-22T10:00:01+00:00",
                    },
                ]
            }

    class ReorderedCore:
        def ordered_tool_steps(self, request, _plan):
            # The second requested tool is independent and sorts before the
            # first requested tool in the validated dependency graph.
            return [
                (2, 3, request.tools[1]),
                (3, 2, request.tools[0]),
            ]

    runner = object.__new__(AgentWorkflowRunner)
    runner.recovery = StoredRun()
    runner.core = ReorderedCore()
    request = AgentPlanRequest(
        goal="Evaluate tools in dependency order",
        tools=[
            {"name": "text.alpha", "payload": {"text": "first in request"}},
            {"name": "text.beta", "payload": {"text": "second in request"}},
        ],
    )

    report = runner._evaluate_workflow_tools(
        uuid4(), request, plan={"dependency_plan": {}}, owner_user_id="owner"
    )

    assert report is not None
    assert report["decision"] == "reject"
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["criteria"][0]["criterion_id"] == "tool-step-2"
    assert report["criteria"][0]["description"] == "Tool execution completed: text.beta"
    assert report["criteria"][0]["status"] == "passed"
    assert report["criteria"][1]["criterion_id"] == "tool-step-3"
    assert report["criteria"][1]["description"] == "Tool execution completed: text.alpha"
    assert report["criteria"][1]["status"] == "failed"
