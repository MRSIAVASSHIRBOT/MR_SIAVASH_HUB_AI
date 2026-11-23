import pytest

from mrhub.agents.replan_cycle import CycleState, assess_cycle


def report(status="unknown", digest=None):
    return {"criteria": [{"criterion_id": "x", "description": "Verify outcome", "status": status, "evidence_digest": digest}]}


def test_success_stops_cycle():
    result = assess_cycle(report("passed", "a" * 64), cycle=1)
    assert result.state is CycleState.COMPLETE


def test_gaps_require_review_before_limit():
    result = assess_cycle(report(), cycle=1)
    assert result.state is CycleState.REVIEW_REQUIRED
    assert "authorization" in result.message


def test_limit_reached_blocks_automatic_retry():
    result = assess_cycle(report(), cycle=3)
    assert result.state is CycleState.LIMIT_REACHED
    assert "human review" in result.message


@pytest.mark.parametrize("cycle,max_cycles", [(-1, 3), (4, 3), (True, 3), (0, 0), (0, 4), (0, True)])
def test_invalid_cycle_parameters(cycle, max_cycles):
    with pytest.raises(ValueError):
        assess_cycle(report(), cycle=cycle, max_cycles=max_cycles)
