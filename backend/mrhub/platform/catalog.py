"""Honest, versioned catalog of first-party capability domains.

The catalog describes product coverage; it does not grant execution permissions.
Maturity labels distinguish existing foundations from finished user-facing services.
"""
from __future__ import annotations

from typing import TypedDict


class CapabilityDomain(TypedDict):
    domain_id: str
    name: str
    purpose: str
    maturity: str
    existing_components: list[str]
    next_steps: list[str]
    safety_boundary: str


_DOMAINS: tuple[CapabilityDomain, ...] = (
    {
        "domain_id": "content",
        "name": "Content and social publishing",
        "purpose": "Create, revise, process, schedule, and publish approved content.",
        "maturity": "foundation",
        "existing_components": ["content drafts and versions", "owner-scoped media assets", "video processing and rendering foundations", "scheduled worker dispatch", "Telegram and opt-in Instagram adapters"],
        "next_steps": ["complete Reels workflow and real-account acceptance", "add more reviewed channel adapters", "improve analytics and content performance feedback"],
        "safety_boundary": "Public publishing remains approval-gated; provider credentials stay server-side.",
    },
    {
        "domain_id": "web",
        "name": "Website creation and management",
        "purpose": "Help users plan, build, test, deploy, and maintain websites.",
        "maturity": "planned",
        "existing_components": ["bounded developer-agent and code-review foundations"],
        "next_steps": ["define website project specification", "add template and asset pipeline", "add isolated preview and test workflow", "add deployment adapters with explicit approval"],
        "safety_boundary": "No arbitrary shell execution or unreviewed deployment; generated changes require review.",
    },
    {
        "domain_id": "automation",
        "name": "Personal and business automation",
        "purpose": "Turn repeatable multi-step tasks into observable, recoverable workflows.",
        "maturity": "foundation",
        "existing_components": ["task and workflow engine", "pull-driven worker", "policy and approval gates", "leases, cancellation, recovery, and audit events"],
        "next_steps": ["scheduled user workflows", "more reusable workflow templates", "in-flight operation stop semantics"],
        "safety_boundary": "Every tool is allow-listed and policy-checked; external side effects require approval.",
    },
    {
        "domain_id": "customer_support",
        "name": "Customer communication and support",
        "purpose": "Help teams organize requests, draft replies, and track support outcomes.",
        "maturity": "planned",
        "existing_components": ["shared authentication, task, memory, knowledge, and tool contracts"],
        "next_steps": ["support inbox adapter", "ticket and conversation model", "human handoff and response approval", "service-quality reporting"],
        "safety_boundary": "No autonomous promises, account changes, or disclosure of customer data without authorization.",
    },
    {
        "domain_id": "business_ops",
        "name": "Business operations",
        "purpose": "Reduce routine administrative work for small businesses and independent workers.",
        "maturity": "planned",
        "existing_components": ["shared project registry, task engine, knowledge store, and audit foundation"],
        "next_steps": ["orders and inventory connectors", "document-backed operational workflows", "owner-approved reporting and exports"],
        "safety_boundary": "Financial, contractual, and irreversible actions remain explicitly owner-controlled.",
    },
    {
        "domain_id": "security",
        "name": "Defensive digital security",
        "purpose": "Provide scoped, evidence-based defensive checks and remediation guidance.",
        "maturity": "foundation",
        "existing_components": ["offline configuration review", "dependency manifest review", "bounded log analysis", "read-only repository analysis"],
        "next_steps": ["approved advisory snapshot review", "authorized asset inventory", "more evidence-linked remediation reports"],
        "safety_boundary": "Only authorized defensive work; no credential theft, malware, stealth, or unauthorized access.",
    },
    {
        "domain_id": "learning",
        "name": "Learning and skill development",
        "purpose": "Explain topics, organize learning resources, and support guided practice.",
        "maturity": "partial",
        "existing_components": ["source-backed knowledge ingestion and retrieval", "owner-scoped memory", "AI model routing"],
        "next_steps": ["learning plans and progress model", "interactive practice engine", "source-quality and answer evaluation"],
        "safety_boundary": "Distinguish sourced facts from generated explanations and preserve citations.",
    },
    {
        "domain_id": "documents",
        "name": "Document and information management",
        "purpose": "Organize, summarize, search, and transform user-authorized information.",
        "maturity": "partial",
        "existing_components": ["source-backed text knowledge store", "FTS5 retrieval and provenance", "memory export and deletion"],
        "next_steps": ["bounded PDF and office document ingestion", "document conversion workflows", "retention and export controls"],
        "safety_boundary": "Uploaded content is untrusted; enforce size limits, owner scoping, and retention rules.",
    },
    {
        "domain_id": "productivity",
        "name": "Personal productivity",
        "purpose": "Help users manage tasks, plans, reminders, and recurring work.",
        "maturity": "partial",
        "existing_components": ["task and workflow engine", "owner-scoped memory", "operator task history and cancellation"],
        "next_steps": ["personal planning interface", "calendar integration", "reminder and recurring-task scheduling"],
        "safety_boundary": "Calendar and message changes require account authorization and user confirmation where appropriate.",
    },
    {
        "domain_id": "multilingual",
        "name": "Translation and localization",
        "purpose": "Make content and digital services usable across languages and regions.",
        "maturity": "planned",
        "existing_components": ["shared model-provider abstraction"],
        "next_steps": ["translation and localization workflows", "terminology and style profiles", "right-to-left layout validation"],
        "safety_boundary": "Preserve source meaning, flag uncertainty, and never silently alter legal or critical wording.",
    },
)


def list_domains() -> list[CapabilityDomain]:
    """Return defensive copies of the canonical product capability catalog."""
    return [
        {**domain, "existing_components": list(domain["existing_components"]), "next_steps": list(domain["next_steps"])}
        for domain in _DOMAINS
    ]


def get_domain(domain_id: str) -> CapabilityDomain | None:
    """Return one domain by stable identifier, without implying feature completeness."""
    for domain in _DOMAINS:
        if domain["domain_id"] == domain_id:
            return {**domain, "existing_components": list(domain["existing_components"]), "next_steps": list(domain["next_steps"])}
    return None
