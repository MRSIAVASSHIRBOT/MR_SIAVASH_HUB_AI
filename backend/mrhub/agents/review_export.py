"""Deterministic bounded review-summary serialization for audit handoffs."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

MAX_BYTES = 100_000
MAX_FINDINGS = 500
MAX_FINDING_TEXT = 500


class ExportError(ValueError):
    """Invalid summary input."""


def export_review_summary(summary: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(summary, Mapping):
        raise ExportError("Summary must be a mapping")
    required = ("revision", "digest", "approved", "findings")
    if any(key not in summary for key in required):
        raise ExportError("Missing required fields")
    rev, digest, approved, findings = (summary[key] for key in required)
    if isinstance(rev, bool) or not isinstance(rev, int) or rev < 1:
        raise ExportError("Invalid revision")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)):
        raise ExportError("Invalid digest")
    if not isinstance(approved, bool):
        raise ExportError("Decision must be boolean")
    if (not isinstance(findings, list) or len(findings) > MAX_FINDINGS
            or not all(isinstance(item, str) and len(item) <= MAX_FINDING_TEXT
                       for item in findings)):
        raise ExportError("Invalid findings")
    envelope = {"schema_version": 1, "revision": rev, "digest": digest,
                "approved": approved, "findings": list(findings)}
    payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise ExportError("Summary too large")
    encoded = payload.encode("utf-8")
    return {"payload": payload, "sha256": hashlib.sha256(encoded).hexdigest(),
            "schema_version": 1}
