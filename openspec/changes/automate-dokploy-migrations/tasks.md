# Tasks

## 1. Migration runner

- [x] 1.1 Add preview-by-default CLI and service for revision inspection, explicit apply, and result verification; test no-op, eligible upgrade, unknown/ahead revision, and multiple heads against disposable PostgreSQL.
- [x] 1.2 Add reviewed revision policy with manual entries for 0023 and 0024; test that missing/manual classifications block the entire pending chain before writes and document how future revisions receive review.
- [x] 1.3 Add bounded advisory locking and support an externally supplied Alembic connection while preserving public version history and normal CLI behavior; test competing runners, lock release, timeout, migration failure, and search_path=app.
- [x] 1.4 Document runner usage, manual migration recovery, and connection requirements; update both environment examples if settings are introduced and check logs contain no connection secrets.

## 2. Production Compose integration

- [x] 2.1 Add production migration service and API/worker success dependencies with identical release image identity; validate merged Compose configuration and preserve existing infrastructure dependencies.
- [x] 2.2 Prove first deployment, same-release redeploy, new release, and failed migration startup ordering with disposable PostgreSQL and synthetic fixtures; verify a fresh gate runs each time and failed migrations block new consumers.
- [x] 2.3 Update docs/deployment.md and AGENTS.md with automatic versus maintenance release procedures, affected-query verification, and recovery instructions; review consistency with existing split and pruning runbooks.

## 3. Dokploy rehearsal and activation instructions

- [ ] 3.1 Record installed Dokploy/Compose versions and the generated deployment command; rehearse a separate deployment and document the supported configuration that guarantees fresh migration checks and failure reporting without recreating unrelated infrastructure.
- [ ] 3.2 Verify API/worker replacement, authenticated project items/detail/category/dashboard reads, and analytics view reads after the rehearsal; fail verification on SQL errors even when health returns 200.
- [x] 3.3 Deliver a production activation checklist covering current revision, manual pending revisions, Neon recovery point for maintenance changes, deployment serialization, and supervised first deployment; confirm no automatic seed/data-split execution is included.

## 4. Final integration checks

- [x] 4.1 Run backend tests, validate development and production Compose overlays using safe environment fixtures, and validate this OpenSpec change; record results and any unverified production-specific acceptance checks.

## Workflow follow-up

- Activate the reviewed configuration in production in a supervised deployment when requested; production credentials and Dokploy settings remain external to Git.
- Enable unattended deployments only after the Dokploy rehearsal and production read checks succeed.
