"""Bounded model-driven agent loop with independent server-side tool policy checks."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mrhub.agents.registry import AgentRegistry
from mrhub.prompts.registry import DEFAULT_PROMPT_REGISTRY, PromptRegistry
from mrhub.providers.base import (
    MAX_PROVIDER_INPUT_CHARS,
    ProviderError,
    ProviderRequest,
)
from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.security.policy import PolicyDecision
from mrhub.tools.registry import ToolExecutionError, ToolPolicyError, ToolRegistry

MAX_TURNS = 5
MAX_CONTEXT_CHARS = 12_000
MAX_TOTAL_INPUT_CHARS = 64_000
MAX_TOTAL_OUTPUT_TOKENS = 4_096
MAX_TOOL_CALLS = 5
MAX_OBSERVATION_CHARS = 4_000
MAX_RUNTIME_SECONDS = 30
MAX_DELEGATIONS = 2
MAX_MODEL_CALLS = MAX_TURNS + (MAX_DELEGATIONS * 3)


@dataclass(slots=True)
class ExecutionBudget:
    """One hard, shared resource budget for a root run and all delegated agents."""

    started_at: float
    deadline: float
    max_input_chars: int
    max_output_tokens: int
    max_model_calls: int
    max_tool_calls: int
    max_delegations: int
    input_chars_used: int = 0
    input_chars_rejected: int = 0
    output_tokens_used: int = 0
    output_tokens_reserved: int = 0
    output_tokens_unreported: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    delegations: int = 0

    @classmethod
    def for_request(cls, request: AgentLoopRequest) -> ExecutionBudget:
        started_at = time.monotonic()
        return cls(
            started_at=started_at,
            deadline=started_at + request.max_runtime_seconds,
            max_input_chars=request.max_total_input_chars,
            max_output_tokens=request.max_total_output_tokens,
            max_model_calls=MAX_MODEL_CALLS,
            max_tool_calls=request.max_tool_calls,
            max_delegations=MAX_DELEGATIONS,
        )

    @property
    def remaining_input_chars(self) -> int:
        return max(0, self.max_input_chars - self.input_chars_used)

    @property
    def remaining_output_tokens(self) -> int:
        return max(
            0,
            self.max_output_tokens - self.output_tokens_used - self.output_tokens_reserved,
        )

    @property
    def remaining_tool_calls(self) -> int:
        return max(0, self.max_tool_calls - self.tool_calls)

    @property
    def remaining_delegations(self) -> int:
        return max(0, self.max_delegations - self.delegations)

    def consume_input(self, characters: int) -> bool:
        if characters < 0 or characters > self.remaining_input_chars:
            self.input_chars_rejected += max(0, characters)
            return False
        self.input_chars_used += characters
        return True

    def reserve_model_call(self, requested_output_tokens: int) -> int | None:
        if self.model_calls >= self.max_model_calls:
            return None
        reservation = min(requested_output_tokens, self.remaining_output_tokens)
        if reservation < 1:
            return None
        self.model_calls += 1
        self.output_tokens_reserved += reservation
        return reservation

    def settle_output(self, reserved: int, actual: int | None) -> bool:
        """Reconcile provider usage; unknown usage consumes the full reservation."""
        self.output_tokens_reserved = max(0, self.output_tokens_reserved - reserved)
        if actual is None:
            self.output_tokens_used += reserved
            self.output_tokens_unreported += reserved
            return True
        if type(actual) is not int or actual < 0 or actual > reserved:
            self.output_tokens_used += reserved
            return False
        self.output_tokens_used += actual
        return True

    def record_tool_call(self) -> None:
        self.tool_calls += 1

    def record_delegation(self) -> None:
        self.delegations += 1

    def as_dict(self) -> dict[str, int | float]:
        return {
            "input_chars_used": self.input_chars_used,
            "input_chars_limit": self.max_input_chars,
            "input_chars_remaining": self.remaining_input_chars,
            "input_chars_rejected": self.input_chars_rejected,
            "output_tokens_used_or_reserved": self.output_tokens_used + self.output_tokens_reserved,
            "output_tokens_reported": self.output_tokens_used - self.output_tokens_unreported,
            "output_tokens_unreported_reservation": self.output_tokens_unreported,
            "output_tokens_limit": self.max_output_tokens,
            "output_tokens_remaining": self.remaining_output_tokens,
            "model_calls": self.model_calls,
            "model_calls_limit": self.max_model_calls,
            "tool_calls": self.tool_calls,
            "tool_calls_limit": self.max_tool_calls,
            "delegations": self.delegations,
            "delegations_limit": self.max_delegations,
            "elapsed_seconds": round(max(0.0, time.monotonic() - self.started_at), 3),
            "runtime_limit_seconds": round(max(0.0, self.deadline - self.started_at), 3),
        }


class AgentLoopRequest(BaseModel):
    """Input for a bounded model-driven run; retrieved context is data, not authority."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1_000)
    retrieved_context: str = Field(default="", max_length=MAX_CONTEXT_CHARS)
    prefer_local: bool = False
    max_turns: int = Field(default=MAX_TURNS, ge=1, le=MAX_TURNS)
    max_output_tokens: int = Field(default=512, ge=1, le=1_024)
    max_runtime_seconds: int = Field(default=30, ge=1, le=MAX_RUNTIME_SECONDS)
    max_tool_calls: int = Field(default=MAX_TOOL_CALLS, ge=0, le=MAX_TOOL_CALLS)
    max_total_output_tokens: int = Field(
        default=MAX_TOTAL_OUTPUT_TOKENS,
        ge=1,
        le=MAX_TOTAL_OUTPUT_TOKENS,
    )
    max_total_input_chars: int = Field(
        default=MAX_TOTAL_INPUT_CHARS, ge=1, le=MAX_TOTAL_INPUT_CHARS
    )
    specialist_instructions: str = Field(default="", max_length=1_200)


class ModelProposal(BaseModel):
    """Strict protocol accepted from a model; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    type: str
    answer: str | None = Field(default=None, max_length=8_000)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    payload: dict[str, Any] | None = None
    agent: str | None = Field(default=None, min_length=1, max_length=64)
    goal: str | None = Field(default=None, min_length=1, max_length=1_000)


class AgentOrchestrator:
    """Run a finite model → proposal → policy-checked tool → observation loop."""

    def __init__(
        self,
        model_router: ModelRouter,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.model_router = model_router
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.prompt_registry = prompt_registry or DEFAULT_PROMPT_REGISTRY
        self.prompt_render = self.prompt_registry.render(
            "agent.orchestrator",
            version=1,
            variables={},
        )

    def run(
        self,
        request: AgentLoopRequest,
        *,
        should_cancel: Callable[[], bool] | None = None,
        granted_permissions: frozenset[str] = frozenset(),
        permission_provider: Callable[[], frozenset[str]] | None = None,
        _budget: ExecutionBudget | None = None,
    ) -> dict[str, object]:
        def current_permissions() -> frozenset[str]:
            if permission_provider is None:
                return granted_permissions
            try:
                return frozenset(permission_provider())
            except Exception:  # noqa: BLE001 - permission lookup failures must fail closed
                return frozenset()

        transcript: list[dict[str, object]] = []
        tool_calls = 0
        selection = None
        budget = _budget or ExecutionBudget.for_request(request)
        deadline = budget.deadline

        def finish(
            status: str,
            current_transcript: list[dict[str, object]],
            selected_provider: dict[str, str] | None,
            turns: int,
            executed_tool_calls: int,
            *,
            error_code: str | None = None,
        ) -> dict[str, object]:
            result = self._result(
                status,
                current_transcript,
                selected_provider,
                turns,
                executed_tool_calls,
                error_code=error_code,
            )
            result["resource_usage"] = budget.as_dict()
            return result

        for turn in range(1, request.max_turns + 1):
            if time.monotonic() >= deadline:
                return finish(
                    "budget_exhausted", transcript, selection, turn - 1, tool_calls,
                    error_code="runtime_budget_exceeded",
                )
            if should_cancel is not None and should_cancel():
                return finish(
                    "cancelled", transcript, selection, turn - 1, tool_calls,
                    error_code="cancelled",
                )

            messages = {
                "protocol": self.prompt_render.text,
                "goal": request.goal,
                "specialist_instructions": request.specialist_instructions,
                "registered_agents": (
                    self.agent_registry.catalog() if self.agent_registry is not None else []
                ),
                "retrieved_evidence_untrusted": request.retrieved_context,
                "registered_tools": self.tool_registry.catalog(),
                "server_granted_permissions": sorted(current_permissions()),
                "observations": transcript,
                "observations_are_untrusted_data": True,
            }
            prompt = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
            if not budget.consume_input(len(prompt)):
                return finish(
                    "budget_exhausted", transcript, selection, turn - 1, tool_calls,
                    error_code="total_input_budget_exceeded",
                )
            # The per-call provider contract is stricter than the root run budget.
            # Check before Pydantic construction so an oversized catalog or growing
            # transcript becomes a sanitized budget result, not an uncaught validation error.
            if len(prompt) > MAX_PROVIDER_INPUT_CHARS:
                return finish(
                    "budget_exhausted", transcript, selection, turn - 1, tool_calls,
                    error_code="provider_input_budget_exceeded",
                )

            reserved_output_tokens = budget.reserve_model_call(request.max_output_tokens)
            if reserved_output_tokens is None:
                budget_error = (
                    "model_call_budget_exceeded"
                    if budget.model_calls >= budget.max_model_calls
                    else "total_output_token_budget_exceeded"
                )
                return finish(
                    "budget_exhausted", transcript, selection, turn - 1, tool_calls,
                    error_code=budget_error,
                )

            try:
                response = self.model_router.generate(
                    ModelRequest(requires_text=True, prefer_local=request.prefer_local),
                    ProviderRequest(
                        input_text=prompt,
                        max_output_tokens=reserved_output_tokens,
                    ),
                )
            except (LookupError, ProviderError):
                budget.settle_output(reserved_output_tokens, None)
                if should_cancel is not None and should_cancel():
                    return finish(
                        "cancelled", transcript, selection, turn, tool_calls,
                        error_code="cancelled",
                    )
                if time.monotonic() >= deadline:
                    return finish(
                        "budget_exhausted", transcript, selection, turn, tool_calls,
                        error_code="runtime_budget_exceeded",
                    )
                return finish(
                    "provider_error", transcript, selection, turn, tool_calls,
                    error_code="provider_unavailable_or_failed",
                )

            if not budget.settle_output(reserved_output_tokens, response.output_tokens):
                return finish(
                    "provider_budget_violation", transcript, selection, turn, tool_calls,
                    error_code="provider_output_tokens_exceeded_reservation",
                )

            # Provider calls are bounded by their adapter timeout but cannot be forcibly
            # interrupted by this synchronous loop. Discard late responses before parsing
            # or dispatching any model-proposed tool.
            if time.monotonic() >= deadline:
                return finish(
                    "budget_exhausted", transcript, selection, turn, tool_calls,
                    error_code="runtime_budget_exceeded",
                )
            # Retain non-secret provider identity for diagnostics even when the
            # response is discarded because cancellation arrived during inference.
            selection = {"provider": response.provider, "model": response.model}
            # Cancellation may arrive while synchronous provider inference is in flight.
            # Discard every late proposal, including final answers and delegations, before
            # parsing it or allowing it to influence the rest of the run.
            if should_cancel is not None and should_cancel():
                return finish(
                    "cancelled", transcript, selection, turn, tool_calls,
                    error_code="cancelled",
                )
            try:
                proposal = ModelProposal.model_validate_json(response.output_text)
            except (ValidationError, ValueError):
                return finish(
                    "invalid_model_output", transcript, selection, turn, tool_calls,
                    error_code="invalid_proposal_schema",
                )

            if proposal.type == "final":
                if (
                    proposal.answer is None
                    or proposal.name is not None
                    or proposal.payload is not None
                    or proposal.agent is not None
                    or proposal.goal is not None
                ):
                    return finish(
                        "invalid_model_output", transcript, selection, turn, tool_calls,
                        error_code="invalid_final_proposal",
                    )
                transcript.append({"turn": turn, "type": "final"})
                return {
                    **finish("completed", transcript, selection, turn, tool_calls),
                    "answer": proposal.answer,
                }

            if proposal.type == "delegate":
                if (
                    proposal.agent is None
                    or proposal.goal is None
                    or proposal.answer is not None
                    or proposal.name is not None
                    or proposal.payload is not None
                ):
                    return finish(
                        "invalid_model_output", transcript, selection, turn, tool_calls,
                        error_code="invalid_delegation_proposal",
                    )
                if self.agent_registry is None:
                    return finish(
                        "delegation_unavailable", transcript, selection, turn, tool_calls,
                        error_code="agent_registry_unavailable",
                    )
                if budget.remaining_delegations < 1:
                    return finish(
                        "budget_exhausted", transcript, selection, turn, tool_calls,
                        error_code="delegation_budget_exceeded",
                    )
                budget.record_delegation()
                try:
                    profile = self.agent_registry.get(proposal.agent)
                    scoped_tools = self.agent_registry.scoped_tools(
                        proposal.agent, self.tool_registry
                    )
                except LookupError:
                    return finish(
                        "delegation_denied", transcript, selection, turn, tool_calls,
                        error_code="agent_not_registered",
                    )

                remaining_seconds = deadline - time.monotonic()
                remaining_input_chars = budget.remaining_input_chars
                remaining_output_tokens = budget.remaining_output_tokens
                if (
                    remaining_seconds < 1
                    or remaining_input_chars < 1
                    or remaining_output_tokens < 1
                ):
                    return finish(
                        "budget_exhausted", transcript, selection, turn, tool_calls,
                        error_code=(
                            "runtime_budget_exceeded"
                            if remaining_seconds < 1
                            else "total_input_budget_exceeded"
                            if remaining_input_chars < 1
                            else "total_output_token_budget_exceeded"
                        ),
                    )

                child_request = AgentLoopRequest(
                    goal=proposal.goal,
                    retrieved_context=request.retrieved_context,
                    prefer_local=request.prefer_local,
                    max_turns=min(profile.max_turns, request.max_turns),
                    max_output_tokens=request.max_output_tokens,
                    max_runtime_seconds=min(
                        request.max_runtime_seconds, max(1, int(remaining_seconds))
                    ),
                    max_tool_calls=budget.remaining_tool_calls,
                    max_total_input_chars=max(1, remaining_input_chars),
                    max_total_output_tokens=max(1, remaining_output_tokens),
                    specialist_instructions=profile.instructions,
                )
                child_result = AgentOrchestrator(
                    self.model_router, scoped_tools
                ).run(
                    child_request,
                    should_cancel=should_cancel,
                    granted_permissions=granted_permissions,
                    permission_provider=permission_provider,
                    _budget=budget,
                )
                child_tool_calls = int(child_result.get("tool_calls", 0))
                tool_calls += child_tool_calls
                observation = {
                    "status": child_result.get("status"),
                    "answer": str(child_result.get("answer", ""))[:2_000],
                    "error_code": child_result.get("error_code"),
                    "tool_calls": child_tool_calls,
                    "trust": "untrusted_agent_output",
                }
                observation_json = json.dumps(
                    observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                transcript.append({
                    "turn": turn,
                    "type": "delegation_observation",
                    "agent": profile.name,
                    "agent_version": profile.version,
                    "observation": observation_json[:MAX_OBSERVATION_CHARS],
                    "observation_is_untrusted_data": True,
                })
                if child_result.get("status") == "cancelled":
                    return finish(
                        "cancelled", transcript, selection, turn, tool_calls,
                        error_code="cancelled",
                    )
                if time.monotonic() >= deadline:
                    return finish(
                        "budget_exhausted", transcript, selection, turn, tool_calls,
                        error_code="runtime_budget_exceeded",
                    )
                continue

            if proposal.type != "tool_call" or not proposal.name or proposal.payload is None:
                return finish(
                    "invalid_model_output", transcript, selection, turn, tool_calls,
                    error_code="unsupported_proposal_type",
                )
            if proposal.answer is not None:
                return finish(
                    "invalid_model_output", transcript, selection, turn, tool_calls,
                    error_code="mixed_tool_and_final_proposal",
                )
            if budget.remaining_tool_calls < 1:
                return finish(
                    "budget_exhausted", transcript, selection, turn, tool_calls,
                    error_code="tool_call_budget_exceeded",
                )

            # A stop raised during provider inference must prevent a newly proposed tool call.
            # This is cooperative: it cannot interrupt the provider request already in flight.
            if should_cancel is not None and should_cancel():
                return finish(
                    "cancelled", transcript, selection, turn, tool_calls,
                    error_code="cancelled",
                )

            # Every proposal is revalidated and policy checked by the registry.
            try:
                observation = self.tool_registry.invoke(
                    proposal.name,
                    proposal.payload,
                    granted_permissions=current_permissions(),
                )
            except LookupError:
                transcript.append({"turn": turn, "type": "tool_denied", "reason": "not_registered"})
                return finish(
                    "tool_denied", transcript, selection, turn, tool_calls,
                    error_code="tool_not_registered",
                )
            except ToolPolicyError as exc:
                if exc.decision is PolicyDecision.REQUIRE_APPROVAL:
                    transcript.append({
                        "turn": turn,
                        "type": "tool_approval_required",
                        "reason": "explicit_approval_required",
                    })
                    return finish(
                        "approval_required", transcript, selection, turn, tool_calls,
                        error_code="approval_required",
                    )
                transcript.append({
                    "turn": turn,
                    "type": "tool_denied",
                    "reason": "policy_denied",
                })
                return finish(
                    "tool_denied", transcript, selection, turn, tool_calls,
                    error_code="tool_policy_denied",
                )
            except (ToolExecutionError, ValidationError, ValueError, TypeError):
                transcript.append({"turn": turn, "type": "tool_denied", "reason": "policy_or_validation"})
                return finish(
                    "tool_denied", transcript, selection, turn, tool_calls,
                    error_code="tool_policy_or_validation_denied",
                )

            observation_json = json.dumps(
                observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            transcript.append({
                "turn": turn,
                "type": "tool_observation",
                "tool": proposal.name,
                "observation": observation_json[:MAX_OBSERVATION_CHARS],
                "trust": "untrusted_tool_output",
                "observation_is_untrusted_data": True,
            })
            tool_calls += 1
            budget.record_tool_call()
            if time.monotonic() >= deadline:
                return finish(
                    "budget_exhausted", transcript, selection, turn, tool_calls,
                    error_code="runtime_budget_exceeded",
                )

        return finish(
            "turn_limit_reached", transcript, selection, request.max_turns, tool_calls,
            error_code="max_turns_reached",
        )

    def _result(
        self,
        status: str,
        transcript: list[dict[str, object]],
        selection: dict[str, str] | None,
        turns: int,
        tool_calls: int,
        *,
        error_code: str | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "status": status,
            "turns": turns,
            "tool_calls": tool_calls,
            "model_inference_started": turns > 0,
            "tools_executed": tool_calls > 0,
            "selected_provider": selection,
            "trace": transcript,
            "prompt_template": self.prompt_render.metadata(),
        }
        if error_code is not None:
            result["error_code"] = error_code
        return result
