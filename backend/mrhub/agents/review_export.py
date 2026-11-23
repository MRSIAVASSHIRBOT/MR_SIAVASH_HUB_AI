"""Deterministic, bounded review-summary serialization for audit handoffs.

The SHA-256 value is a content checksum, not an authentication token or signature.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

MAX_BYTES = 100_000
MAX_FINDINGS = 500
MAX_FINDING_TEXT = 500
SCHEMA_VERSION = 1


class ExportError(ValueError):
    """Raised when a review summary cannot be exported safely."""


def export_review_summary(summary: Mapping[str, object]) -> dict[str, object]:
    """Serialize a validated review summary deterministically within fixed bounds."""
    if not isinstance(summary, Mapping):
        raise ExportError("Summary must be a mapping")

    required = ("revision", "digest", "approved", "findings")
    if any(key not in summary for key in required):
        raise ExportError("Missing required fields")

    revision = summary["revision"]
    digest = summary["digest"]
    approved = summary["approved"]
    findings = summary["findings"]

    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ExportError("Invalid revision")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
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
