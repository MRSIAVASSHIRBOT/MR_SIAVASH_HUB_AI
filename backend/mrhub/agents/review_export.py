"""Deterministic bounded review-summary serialization for audit handoffs."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

SCHEMA_VERSION = 1
MAX_BYTES = 100_000
MAX_FINDINGS = 500
MAX_FINDING_TEXT = 500


class ExportError(ValueError):
    """Raised when review-summary data violates the export contract."""


def export_review_summary(summary: Mapping[str, object]) -> dict[str, object]:
    """Serialize a validated review summary and return its SHA-256 checksum.

    The checksum supports integrity comparison during handoff; it is not a
    digital signature, authentication mechanism, or authorization decision.
    """
    if not isinstance(summary, Mapping):
        raise ExportError("Summary must be a mapping")

    required = ("revision", "digest", "approved", "findings")
    if set(summary) != set(required):
        raise ExportError("Summary fields do not match the export schema")

    revision, digest, approved, findings = (summary[key] for key in required)

    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ExportError("Invalid revision")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise ExportError("Invalid digest")
    if not isinstance(approved, bool):
        raise ExportError("Decision must be boolean")
    if (
        not isinstance(findings, list)
        or len(findings) > MAX_FINDINGS
        or not all(
            isinstance(item, str) and len(item) <= MAX_FINDING_TEXT
            for item in findings
        )
    ):
        raise ExportError("Invalid findings")

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "digest": digest,
        "approved": approved,
        "findings": list(findings),
    }
    try:
        # Reject lone UTF-16 surrogates rather than letting JSON escape them
        # into a payload that is not a valid UTF-8 representation of the text.
        for finding in findings:
            finding.encode("utf-8")
        payload = json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        encoded = payload.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ExportError("Summary cannot be encoded as UTF-8 JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise ExportError("Summary too large")

    return {
        "payload": payload,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "schema_version": SCHEMA_VERSION,
    }
