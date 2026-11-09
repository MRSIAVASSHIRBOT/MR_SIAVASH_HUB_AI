# ADR-0009: Owner-scoped reviewable agent proposal lifecycle

- Status: Implemented on the feature branch; pending CI and review
- Date: 2026-11-09

## Decision

Persist bounded specialist-agent proposals in the canonical versioned SQLite schema. Every record is scoped to its authenticated owner. The API exposes create, list, retrieve, and review operations. Reviews are one-time decisions bound to a SHA-256 fingerprint of the proposal identifier and canonical payload.

## Security boundaries

- All routes require the existing bearer-session authentication dependency.
- Database reads and writes include the authenticated owner identifier.
- Proposal definitions are revalidated against the current server-defined agent and tool registries on creation and approval.
- Unknown tools cannot be proposed; no dynamic tool installation or permission grant exists.
- Approval records review intent only. The candidate remains inactive and is not inserted into the live agent registry.
- A stale fingerprint, cross-owner identifier, duplicate pending/approved name, or second review is rejected.
- Audit events record lifecycle transitions without copying proposal instructions or rationale into audit metadata.

## Follow-up

A separately designed activation operation must revalidate policy and permissions at execution time, enforce resource/delegation budgets, and remain distinct from proposal approval.
