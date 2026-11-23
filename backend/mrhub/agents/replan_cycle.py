"""Bounded, human-gated AWI replanning cycle state.

This module only transitions advisory state. It never dispatches execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mrhub.agents.replanning import ReplanProposal, propose_replan

MAX_REPLAN_CYCLES = 3


class CycleState(StrEnum):
    COMPLETE = "complete"
    REVIEW_REQUIRED = "review_required"
    LIMIT_REACHED = "limit_reached"


@dataclass(frozen=True)
class ReplanCycleResult:
    cycle: int
    state: CycleState
    proposal: ReplanProposal | None
    message: str


def assess_cycle(report: dict[str, object], *, cycle: int, max_cycles: int = MAX_REPLAN_CYCLES) -> ReplanCycleResult:
    """Assess report and produce a bounded advisory result; no execution occurs."""
    if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle < 0:
        raise ValueError("cycle must be a non-negative integer")
    if isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or not 1 <= max_cycles <= MAX_REPLAN_CYCLES:
        raise ValueError(f"max_cycles must be between 1 and {MAX_REPLAN_CYCLES}")
    if cycle > max_cycles:
        raise ValueError("cycle cannot exceed max_cycles")

    proposal = propose_replan(report)
    if not proposal.needs_replanning:
        return ReplanCycleResult(cycle, CycleState.COMPLETE, proposal, proposal.summary)
    if cycle >= max_cycles:
        return ReplanCycleResult(
            cycle, CycleState.LIMIT_REACHED, proposal,
            f"Cycle limit ({max_cycles}) reached; human review is required.",
        )
    return ReplanCycleResult(
        cycle, CycleState.REVIEW_REQUIRED, proposal,
        "A revised plan may be proposed for review; execution requires separate authorization.",
    )
