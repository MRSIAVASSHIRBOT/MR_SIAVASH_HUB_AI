# ADR 0004: Versioned SQLite Schema Migrations

- Status: Accepted
- Date: 2026-11-01

## Context

The repository initially created tables and applied compatibility changes directly from repository and worker initialization code. As the application grows, ad-hoc DDL makes schema history difficult to review, test, and reproduce. A partial upgrade must not leave a database in an ambiguous state.

## Decision

Use one migration coordinator, `mrhub.infrastructure.migrations.SchemaMigrator`, for versioned SQLite schema changes.

Each migration has a strictly increasing version, stable name, and SHA-256 checksum. Each pending migration is applied in its own `BEGIN IMMEDIATE` transaction. Its history row is written in that same transaction after all statements succeed. Existing databases are upgraded through an idempotent baseline that preserves existing rows and adds missing compatibility columns. Unknown future versions and checksum drift fail closed.

## Consequences

- Startup can deterministically bring a compatible database to the current schema.
- Failed migration statements roll back their DDL and history row.
- Migration history can be inspected using the `schema_migrations` table.
- Migration definitions become immutable after release; corrections require a new migration.
- Migrations are forward-only for now. No automatic downgrade or backup/restore workflow is claimed.
- The worker's current defensive table initialization remains compatible, but future schema changes should be added to the central migration registry.

## Review triggers

Revisit this decision when PostgreSQL is introduced, when multiple application versions may concurrently migrate the same database, or when online/zero-downtime migrations become necessary.
