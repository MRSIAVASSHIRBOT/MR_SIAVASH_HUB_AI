"""Bounded, non-applying Python patch proposals for human review.

This module compares caller-supplied source text only. It never reads arbitrary paths,
imports target modules, executes code, or writes files.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
from collections import Counter
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from mrhub.nexus.static_analysis import analyze_python_source

MAX_SOURCE_CHARS = 64_000
MAX_DIFF_CHARS = 80_000


class PatchProposalError(ValueError):
    """Raised when a proposed diff exceeds the supported safe review contract."""


def _validate_label(path: str) -> str:
    if not path or len(path) > 200 or "\\" in path or "\x00" in path:
        raise PatchProposalError("invalid_path_label")
    label = PurePosixPath(path)
    if label.is_absolute() or any(part in {"", ".", ".."} for part in label.parts):
        raise PatchProposalError("invalid_path_label")
    if label.suffix != ".py":
        raise PatchProposalError("python_file_required")
    return label.as_posix()


def _syntax_status(source: str) -> dict[str, Any]:
    try:
        ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return {
            "status": "syntax_error",
            "line": max(1, getattr(exc, "lineno", None) or 1),
            "message": "Python syntax could not be parsed; source was not executed.",
        }
    return {"status": "ok", "line": None, "message": None}


def _finding_key(finding: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(finding.get("rule_id", "")),
        str(finding.get("severity", "")),
        str(finding.get("message", "")),
    )


def _finding_delta(
    primary: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    remaining = Counter(_finding_key(item) for item in comparison)
    delta: list[dict[str, Any]] = []
    for item in primary:
        key = _finding_key(item)
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            delta.append(item)
    return delta


def create_patch_proposal(
    path: str,
    original_source: str,
    proposed_source: str,
) -> dict[str, Any]:
    """Return a bounded unified diff and syntax metadata without applying the patch."""
    safe_path = _validate_label(path)
    if len(original_source) > MAX_SOURCE_CHARS or len(proposed_source) > MAX_SOURCE_CHARS:
        raise PatchProposalError("source_too_large")

    diff = "".join(
        difflib.unified_diff(
            original_source.splitlines(keepends=True),
            proposed_source.splitlines(keepends=True),
            fromfile=f"a/{safe_path}",
            tofile=f"b/{safe_path}",
            n=3,
        )
    )
    if len(diff) > MAX_DIFF_CHARS:
        raise PatchProposalError("diff_too_large")

    base_review = analyze_python_source(original_source, path=safe_path)
    proposed_review = analyze_python_source(proposed_source, path=safe_path)
    introduced_findings = _finding_delta(
        proposed_review["findings"], base_review["findings"]
    )
    resolved_findings = _finding_delta(
        base_review["findings"], proposed_review["findings"]
    )
    introduced_high_count = sum(
        finding["severity"] == "high" for finding in introduced_findings
    )
    review_status = (
        "complete"
        if base_review["status"] == "ok" and proposed_review["status"] == "ok"
        else "partial"
    )

    proposal_id = str(uuid4())
    return {
        "proposal_id": proposal_id,
        "path": safe_path,
        "base_sha256": hashlib.sha256(original_source.encode("utf-8")).hexdigest(),
        "proposed_sha256": hashlib.sha256(proposed_source.encode("utf-8")).hexdigest(),
        "base_syntax": _syntax_status(original_source),
        "proposed_syntax": _syntax_status(proposed_source),
        "static_review": {
            "status": review_status,
            "base_findings": base_review["findings"],
            "proposed_findings": proposed_review["findings"],
            "introduced_findings": introduced_findings,
            "resolved_findings": resolved_findings,
            "introduced_high_severity_count": introduced_high_count,
            "human_review_required": True,
            "code_executed": False,
        },
        "diff": diff,
        "changed": original_source != proposed_source,
        "source_stored": False,
        "proposal_persisted": False,
        "code_executed": False,
        "files_modified": False,
    }
