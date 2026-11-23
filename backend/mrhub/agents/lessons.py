"""Evidence-linked lessons learned proposals; never writes memory automatically."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID

from mrhub.memory.repository import MemoryRepository

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STEP_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_CATEGORY_PATTERN = re.compile(r"^[\w .:/-]{1,80}$", re.UNICODE)
MAX_LESSON_TEXT = 500
MIN_LESSON_TEXT = 20


class LessonProposalError(ValueError):
    """Raised when lesson content lacks safe, persisted workflow evidence."""


@dataclass(frozen=True)
class LessonEvidence:
    workflow_id: UUID
    workflow_status: str
    step_id: str
    step_status: str
    output_digest: str | None
    error_code: str | None = None


@dataclass(frozen=True)
class LessonProposal:
    proposal_id: str
    source_reference: str
    evidence_digest: str
    category: str
    lesson_text: str

    def as_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "source_reference": self.source_reference,
            "evidence_digest": self.evidence_digest,
            "memory_entry_preview": {
                "memory_type": "procedural",
                "category": self.category,
                "content": self.lesson_text,
                "provenance": self.source_reference,
                "confidence": 0.5,
                "verification_status": "user_authored",
            },
            "owner_review_required": True,
            "automatic_memory_write": False,
            "execution_authorized": False,
            "limitations": [
                "The digest proves linkage to a persisted successful step output, not the truth or generality of the lesson text.",
                "The lesson text is a user-supplied proposal and must be reviewed before saving.",
                "No raw workflow output, tool payload, prompt, or external account data is retrieved or stored by this preview.",
            ],
        }


def build_lesson_proposal(
    evidence: LessonEvidence,
    *,
    category: str,
    lesson_text: str,
) -> LessonProposal:
    """Build a stable owner-review proposal from a completed, digest-backed step."""
    if evidence.workflow_status != "succeeded" or evidence.step_status != "succeeded":
        raise LessonProposalError("Lessons require a successfully completed workflow step")
    if (
        not isinstance(evidence.step_id, str)
        or not _STEP_KEY_PATTERN.fullmatch(evidence.step_id)
    ):
        raise LessonProposalError("Workflow step identity is invalid")
    if (
        not isinstance(evidence.output_digest, str)
        or not _DIGEST_PATTERN.fullmatch(evidence.output_digest)
    ):
        raise LessonProposalError("A valid persisted output digest is required")
    if evidence.error_code is not None:
        raise LessonProposalError("A step with an error code cannot support a verified lesson")
    if not isinstance(category, str) or not _CATEGORY_PATTERN.fullmatch(category.strip()):
        raise LessonProposalError("Lesson category must be a bounded canonical label")
    normalized_category = category.strip()
    if not isinstance(lesson_text, str):
        raise LessonProposalError("Lesson text must be text")
    normalized_text = lesson_text.strip()
    if not MIN_LESSON_TEXT <= len(normalized_text) <= MAX_LESSON_TEXT:
        raise LessonProposalError(
            f"Lesson text must contain {MIN_LESSON_TEXT} to {MAX_LESSON_TEXT} characters"
        )
    try:
        MemoryRepository.validate_memory_text(normalized_text)
        MemoryRepository.validate_memory_text(normalized_category)
    except (TypeError, ValueError) as exc:
        raise LessonProposalError(
            "Lesson proposal contains unsupported or sensitive content"
        ) from exc

    source_reference = (
        f"workflow://{evidence.workflow_id}/steps/{evidence.step_id}"
        f"?output_sha256={evidence.output_digest}"
    )
    canonical = json.dumps(
        {
            "workflow_id": str(evidence.workflow_id),
            "step_id": evidence.step_id,
            "output_digest": evidence.output_digest,
            "category": normalized_category,
            "lesson_text": normalized_text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    proposal_id = hashlib.sha256(canonical).hexdigest()

    return LessonProposal(
        proposal_id=proposal_id,
        source_reference=source_reference,
        evidence_digest=evidence.output_digest,
        category=normalized_category,
        lesson_text=normalized_text,
    )
