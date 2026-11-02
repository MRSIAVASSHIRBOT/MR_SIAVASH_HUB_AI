"""Bounded, non-applying Python patch proposals for human review.

This module compares caller-supplied source text only. It never reads arbitrary paths,
imports target modules, executes code, or writes files.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

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

    proposal_id = str(uuid4())
    return {
        "proposal_id": proposal_id,
        "path": safe_path,
        "base_sha256": hashlib.sha256(original_source.encode("utf-8")).hexdigest(),
        "proposed_sha256": hashlib.sha256(proposed_source.encode("utf-8")).hexdigest(),
        "base_syntax": _syntax_status(original_source),
        "proposed_syntax": _syntax_status(proposed_source),
        "diff": diff,
        "changed": original_source != proposed_source,
        "source_stored": False,
        "proposal_persisted": False,
        "code_executed": False,
        "files_modified": False,
    }
