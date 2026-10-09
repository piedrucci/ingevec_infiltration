# Proposal

## Why

Production migrations currently require manual container commands. A recent schema removal left running Python processes using an obsolete model; deployment must coordinate migration completion, application replacement, and actual data-query verification.

## What Changes

- Add a production Compose migration service using the same release as the API and PDF worker; require successful completion before new application processes start.
- Add a migration runner with explicit apply mode, revision checks, bounded database locking, and sanitized deployment logs.
- Automatically apply only explicitly reviewed, backward-compatible migration revisions. Block unclassified or manual revisions with actionable instructions; preserve existing one-time data-operation procedures.
- Document and rehearse Dokploy configuration, repeated deployments, failure handling, maintenance releases, and checks that exercise application queries.
- Enable automation only after the installed Dokploy/Compose integration passes the deployment-order acceptance checks.

## Capabilities

### New Capabilities

- `deployment-migrations`: Migration execution and application startup coordination during production deployments.

### Modified Capabilities

None. Existing backend schema, query-validation, ERD, and operational-data requirements continue to apply.

## Impact

Production Compose configuration, an API operational command and supporting service, Alembic connection handling, deployment tests, `docs/deployment.md`, `AGENTS.md`, and environment examples if settings are introduced. No new database objects or business-data transformations are proposed. GitHub remains the source and Dokploy owns production deployment credentials and execution.
