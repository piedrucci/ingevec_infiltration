# Design

## Context

See proposal.md for motivation. `compose.yaml` starts API and worker independently of migrations. `compose.prod.yaml` sets resource limits; neither currently has a migration dependency. The runtime Dockerfile already copies Alembic and migration files. `migrations/env.py` uses the application URL and explicitly stores migration history in `public`.

Dokploy's Compose documentation describes a custom command prefixed with `docker`; it does not establish an arbitrary shell pre-deploy hook. Docker Compose supports dependencies with `service_completed_successfully`. The installed Dokploy and Compose versions and their exact generated command are not available in this workspace.

Sources: https://docs.dokploy.com/docs/core/docker-compose and https://docs.docker.com/compose/how-tos/startup-order/ .

## Goals / Non-Goals

Goals: execute eligible schema migrations once per deployment attempt, gate new processes on success, and verify meaningful data reads. Use existing Dokploy credentials and release builds.

Non-goals: automatic JSON seeds or one-time data transformations, zero-downtime destructive changes, production credentials in GitHub Actions, automatic database downgrade, and a new application schema.

## Decisions

1. **Compose migration service as the deployment gate.** Add a production-only `migrate` service with `restart: "no"`; API and worker depend on its successful completion. Use the same explicit release image identity for all three services, preserving existing dependencies and resource controls. Run a command such as `python -m app.commands.deploy_migrations --apply`. This fits the documented Compose interface. Running Alembic in each API startup risks competing migrations; relying on an unverified Dokploy hook is not a valid implementation assumption.

2. **A fresh gate for each deployment.** Verify same-image redeploy behavior with the installed Compose version and Dokploy-generated configuration. Document a supported command/service recreation configuration that guarantees a fresh migration check, including after a previous successful exit. Preserve Dokploy project name, overlays, networks, and Traefik configuration. Do not blindly force-recreate the entire infrastructure stack. Production activation is blocked until success and failure propagation work in a disposable Dokploy deployment. Compose dependency ordering does not guarantee atomic replacement or preservation of every old container on failure; make no such promise.

3. **Thin CLI, migration service logic.** Implement a non-mutating preview default and explicit `--apply`. Resolve a single head and the complete pending chain before applying anything. Read `public.alembic_version`, reject unknown/ahead/divergent history, and verify the resulting head. Never stamp, downgrade, or automatically retry partially executed migrations.

4. **Reviewed revision policy.** Keep a version-controlled manifest identifying revisions eligible for automatic execution. Missing classification blocks automatic execution. Existing `0023` (data split prerequisite) and `0024` (destructive drop) are manual entries with their runbooks. Policy applies to pending revisions only, so already-applied history does not block a no-op deployment. Do not infer safety solely by scanning SQL. A review must consider compatibility with the currently deployed code, data requirements, lock duration, and analytics consumers.

5. **Database coordination.** Use a PostgreSQL advisory lock with bounded acquisition and connection timeouts; re-read revisions after acquiring it. Use a direct/session-capable migration connection if the normal URL uses transaction pooling. Execute Alembic with the same held SQLAlchemy connection via `Config.attributes`, extending `env.py` while preserving ordinary online/offline invocation and `version_table_schema="public"`. Release the lock in `finally`. Serialize Dokploy deployments too: a database lock alone does not prevent an older release being deployed after a newer one. Document manual migration concurrency restrictions.

6. **Compatible and maintenance releases.** Automatic migrations must support the still-running release. Future removals should first ship code that stops using a field, then remove it in a later reviewed release. For pending `0024`, confirm production revision and the deployed model before proceeding; if old code still needs the column, drain requests/jobs and stop API/worker for a maintenance operation, then apply and start the matching release. Respect the existing `0023` data-split workflow. Recovery after a destructive migration uses a verified Neon recovery point or a reviewed forward fix, never an assumed Alembic downgrade.

7. **Verification beyond health.** Rehearse on disposable PostgreSQL with synthetic data: no-op, compatible upgrade, failure, concurrency, lock timeout, unknown revision, manual revision rejection, and repeat deployments. Exercise project-item listing (including pagination and detail), category items, dashboard reads, and analytics views against the target schema. After deployment, verify real authenticated read paths and worker startup; keep returned business records out of logs.

## Risks / Trade-offs

- Pending destructive revision → stop automatic execution and follow its maintenance runbook with a verified recovery point.
- Completed migration containers reused → prove a fresh check on repeated Dokploy deployments before activation.
- Migration failure during Compose reconciliation → new dependent processes stay blocked, but old-container availability is not guaranteed; provide recovery instructions.
- Transaction-pooled Neon connection → use a session-capable migration URL and validate locking in staging.
- Schema succeeds but app startup fails → retain compatible old-release recovery where possible; do not revert schema automatically.
- New deployment-specific settings → document both environment examples, keeping actual values in Dokploy.

## Migration Plan

1. Implement runner, production gate, policy, tests, and operational documentation locally.
2. Validate Compose overlays with non-secret fixtures and rehearse against disposable PostgreSQL.
3. Capture installed Dokploy/Compose versions and generated command; validate gate behavior in a separate deployment before enabling it in production.
4. Inspect production revision and complete any pending manual migration, including prerequisite data work, through its existing reviewed procedure.
5. Enable the validated production deployment configuration and execute one supervised deployment.
6. Confirm revision, affected authenticated reads, analytics queries, and API/worker startup. Retain sanitized deployment logs. Only then enable unattended deployments for eligible revisions.

If rollout fails, disable automatic deployment, inspect revision and logs, and recover the application using a schema-compatible release. Leave destructive database recovery to the reviewed maintenance procedure.
