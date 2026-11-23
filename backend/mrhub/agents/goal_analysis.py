"""Deterministic, bounded preflight analysis for Goal-to-Prompt Intelligence.

This module produces advisory routing signals only. It does not authorize tools,
select credentials, or claim that research or execution has happened.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.work_order import WorkOrder


Complexity = Literal["low", "moderate", "high"]
Modality = Literal["text", "vision", "audio"]


class ModelRequirements(BaseModel):
    """Input modalities inferred from the request, not a provider authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    modalities: list[Modality] = Field(min_length=1, max_length=3)
    tool_catalog_needed: bool
    provider_selection_needed: bool = True


class GoalDecisionAnalysis(BaseModel):
    """Explainable, deterministic routing and clarification signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    complexity: Complexity
    complexity_score: int = Field(ge=0, le=100)
    research_required: bool
    tool_use_required: bool
    clarification_recommended: bool
    information_gaps: list[str] = Field(max_length=12)
    reason_codes: list[str] = Field(max_length=12)
    model_requirements: ModelRequirements
    analysis_source: Literal["deterministic_heuristic"] = "deterministic_heuristic"
    authorization_checked: Literal[False] = False
    execution_started: Literal[False] = False


_ACTION_TERMS = (
    "build", "create", "implement", "write", "edit", "modify", "update",
    "fix", "debug", "run", "execute", "deploy", "publish", "send", "delete",
    "install", "configure", "connect", "automate", "generate", "convert",
    "design", "analyze", "analyse", "process", "upload", "download",
    "بساز", "ساخت", "ایجاد", "پیاده سازی", "پیاده‌سازی", "بنویس",
    "ویرایش", "تغییر", "به روزرسانی", "به‌روزرسانی", "اصلاح", "رفع",
    "اجرا", "استقرار", "منتشر", "ارسال", "حذف", "نصب", "پیکربندی",
    "اتصال", "خودکار", "تولید", "تبدیل", "طراحی", "تحلیل", "پردازش",
    "بارگذاری", "دانلود",
)
_TOOL_ACTION_TERMS = (
    "build", "create", "implement", "edit", "modify", "update", "fix",
    "debug", "run", "execute", "deploy", "publish", "send", "delete",
    "install", "configure", "connect", "automate", "upload", "download",
    "بساز", "ساخت", "ایجاد", "پیاده سازی", "پیاده‌سازی", "ویرایش",
    "تغییر", "به روزرسانی", "به‌روزرسانی", "اصلاح", "رفع", "اجرا",
    "استقرار", "منتشر", "ارسال", "حذف", "نصب", "پیکربندی", "اتصال",
    "خودکار", "بارگذاری", "دانلود",
)
_RESEARCH_TERMS = (
    "latest", "current", "recent", "today", "yesterday", "this week",
    "compare", "comparison", "benchmark", "research", "investigate",
    "sources", "citations", "official documentation", "release notes",
    "market price", "regulation", "standard", "version history",
    "جدیدترین", "آخرین", "فعلی", "امروز", "دیروز", "این هفته",
    "مقایسه", "تحقیق", "بررسی منابع", "منابع رسمی", "مستندات رسمی",
    "قیمت روز", "قوانین", "استاندارد", "نسخه جدید",
)
_VISION_TERMS = (
    "image", "photo", "picture", "screenshot", "visual", "video frame",
    "تصویر", "عکس", "اسکرین شات", "اسکرین‌شات", "قاب ویدیو",
)
_AUDIO_TERMS = (
    "audio", "speech", "voice recording", "transcribe", "transcription",
    "صدا", "گفتار", "ضبط صوت", "رونویسی", "تبدیل گفتار",
)
_INFORMATION_TERMS = (
    "what is", "what are", "how does", "how do", "why does", "explain",
    "define", "meaning of", "how to", "steps to", "ways to", "what happens if",
    "چیست", "چه هست", "چطور", "چگونه", "چرا", "نحوه", "روش", "مراحل",
    "توضیح بده", "تعریف کن", "معنی",
)
_UNCERTAINTY_TERMS = (
    "unknown", "unspecified", "not specified", "unclear", "to be determined",
    "نامشخص", "تعیین نشده", "مشخص نیست", "هنوز معلوم نیست", "نیاز به تعیین",
)
_HIGH_IMPACT_TERMS = (
    "deploy", "publish", "send", "delete", "purchase", "payment",
    "transfer funds", "change permissions", "انتشار", "ارسال", "حذف",
    "خرید", "پرداخت", "انتقال وجه", "تغییر مجوز",
)


def _normalize(value: str) -> str:
    return (
        value.casefold()
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", " ")
        .replace("\u200f", "")
        .replace("\u200e", "")
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = _normalize(term)
        if " " in normalized or not normalized.isascii():
            if normalized in text:
                return True
        elif re.search(rf"(?<![a-z0-9_]){re.escape(normalized)}(?![a-z0-9_])", text):
            return True
    return False


def analyze_goal(
    goal: str,
    *,
    work_order: WorkOrder | None = None,
) -> GoalDecisionAnalysis:
    """Return transparent advisory signals for a natural-language goal.

    If a validated WorkOrder is supplied, its scope, assumptions, constraints,
    dependencies, acceptance criteria and capability needs refine the signals.
    Every inferred decision is heuristic and must be checked against actual
    tools, grants, policy, user confirmation and evidence before execution.
    """
    if not isinstance(goal, str):
        raise TypeError("goal must be text")
    normalized_goal = goal.strip()
    if not normalized_goal or len(normalized_goal) > 1_000:
        raise ValueError("goal must contain 1 to 1000 characters")

    normalized = _normalize(normalized_goal)
    work_order_text: list[str] = []
    assumptions: list[str] = []
    constraints: list[str] = []
    dependencies: list[str] = []
    capability_count = 0
    criterion_count = 0
    verification_count = 0
    scope = ""

    if work_order is not None:
        if _normalize(work_order.goal) != normalized:
            raise ValueError("work_order goal must match the analyzed goal")
        scope = work_order.scope.strip()
        assumptions = list(work_order.assumptions)
        constraints = list(work_order.constraints)
        dependencies = list(work_order.dependencies)
        capability_count = len(work_order.required_capabilities)
        criterion_count = len(work_order.acceptance_criteria)
        verification_count = len(work_order.verification_steps)
        work_order_text = [
            work_order.intent,
            work_order.scope,
            *assumptions,
            *constraints,
            *dependencies,
            *work_order.required_capabilities,
            *work_order.acceptance_criteria,
            *work_order.verification_steps,
        ]

    combined = _normalize(" ".join([normalized_goal, *work_order_text]))
    action_required = _contains_any(normalized, _ACTION_TERMS)
    research_required = _contains_any(combined, _RESEARCH_TERMS)
    vision_required = _contains_any(normalized, _VISION_TERMS)
    audio_required = _contains_any(normalized, _AUDIO_TERMS)
    information_request = _contains_any(normalized, _INFORMATION_TERMS)
    tool_action_signal = _contains_any(normalized, _TOOL_ACTION_TERMS)
    # An instructional question can mention action verbs without requesting the
    # Agent to perform the action. Explicit WorkOrder capabilities still count.
    tool_use_required = capability_count > 0 or (tool_action_signal and not information_request)
    high_impact = _contains_any(combined, _HIGH_IMPACT_TERMS)

    information_gaps: list[str] = []
    reason_codes: list[str] = []

    if (
        not action_required
        and not research_required
        and not vision_required
        and not audio_required
        and not information_request
    ):
        information_gaps.append("requested_outcome")
        reason_codes.append("goal_has_no_detected_action_or_research_signal")
    elif information_request:
        reason_codes.append("general_information_request")

    if work_order is not None and tool_use_required and not scope:
        information_gaps.append("target_scope")
        reason_codes.append("action_scope_not_specified")

    if any(
        _contains_any(_normalize(item), _UNCERTAINTY_TERMS)
        for item in assumptions + constraints
    ):
        information_gaps.append("unresolved_assumption_or_constraint")
        reason_codes.append("work_order_contains_unresolved_information")

    if high_impact and tool_use_required and (work_order is None or not scope):
        information_gaps.append("high_impact_action_scope")
        reason_codes.append("high_impact_scope_requires_review")

    if research_required:
        reason_codes.append("freshness_or_external_evidence_signal")
    if tool_use_required:
        reason_codes.append("action_or_capability_signal")
    if capability_count:
        reason_codes.append("registered_tool_capability_assessment_needed")
    if vision_required:
        reason_codes.append("visual_input_signal")
    if audio_required:
        reason_codes.append("audio_input_signal")

    # A bounded transparent heuristic: scope size and verification/dependency
    # burden increase the score; this is not a learned estimate or SLA prediction.
    score = 5
    score += min(20, len(normalized_goal) // 40)
    conjunction_pattern = r"\b(and|then|also|plus)\b|(?<!\w)و(?!\w)|سپس|همچنین"
    conjunction_count = len(re.findall(conjunction_pattern, normalized))
    score += min(20, conjunction_count * 5)
    score += min(15, len(dependencies) * 4)
    score += min(15, capability_count * 5)
    score += min(10, len(constraints) * 2)
    score += min(10, criterion_count * 2)
    score += min(5, verification_count)
    if high_impact and tool_use_required:
        score += 10
    score = min(100, score)

    complexity: Complexity
    if score < 30:
        complexity = "low"
    elif score < 60:
        complexity = "moderate"
    else:
        complexity = "high"

    modalities: list[Modality] = ["text"]
    if vision_required:
        modalities.append("vision")
    if audio_required:
        modalities.append("audio")

    return GoalDecisionAnalysis(
        complexity=complexity,
        complexity_score=score,
        research_required=research_required,
        tool_use_required=tool_use_required,
        clarification_recommended=bool(information_gaps),
        information_gaps=information_gaps,
        reason_codes=list(dict.fromkeys(reason_codes)),
        model_requirements=ModelRequirements(
            modalities=modalities,
            tool_catalog_needed=tool_use_required,
        ),
    )
