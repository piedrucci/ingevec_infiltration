# Project archived

Archived on 2026-11-22. Production was stopped and nothing is deployed. This file records what exists and how to bring it back.

## State at archive time

- Dokploy compose project `ingevec-postventa-production` is stopped, not deleted. Its six volumes were kept on the Hostinger VPS: `keycloak_data`, `nats_data`, `redis_data`, `seaweedfs_data`, `superset_db_data`, `superset_home`.
- Neon project `Ingevec` (AWS US East 2, Postgres 18): branches `production` (default) and `development`. The compute is suspended when idle. A snapshot of `production` was taken at archive time.
- Public domains `app`, `api`, `auth` and `bi` on `capix.cloud` return an error page.

## Backups (private, not in Git)

Kept outside this repository on the maintainer's machine and on a second copy:

- Neon `production` dump (`pg_dump` custom format, Postgres 18 client) with SHA-256 and row counts (items 681, source rows 1233, documents 62, cause links 759, projects 51).
- SeaweedFS data tarball (PDFs and source workbooks), Keycloak database dump, Superset database dump, Superset home tarball, with a `SHA256SUMS` file.
- Superset dashboard export ZIP (dashboard, charts, datasets, database connection).
- Dokploy environment variables, stored separately in encrypted storage. They are not in this repo.

These files contain business data. Keep them private.

## Restore order

1. Restore the database: from the Neon snapshot, or by restoring the dump into the Neon project with a Postgres 18 `pg_restore`. Compare row counts afterwards.
2. Recreate the Dokploy compose project from this repository (`compose.yaml` + `compose.prod.yaml`) and re-enter the saved environment variables. If the VPS volumes are gone, restore the SeaweedFS, Keycloak and Superset tarballs/dumps into new volumes first.
3. Follow `docs/deployment.md`. The migration policy in `AGENTS.md` still applies: do not stamp Alembic revisions to bypass discrepancies, and keep manual revisions manual.
4. Keep `SUPERSET_EMBEDDING_ENABLED=false` until the checks in `docs/superset-analytics.md` are complete. Import the Superset dashboard ZIP following `docs/superset-analytics.md` (map database and dataset UUIDs first).
5. Verify `https://api.capix.cloud/health`, a non-admin viewer's row scope in Superset, and the PDF/item link totals.

## Not covered

- Redis cache and NATS in-flight events were not backed up (cache and transient events).
- Superset reader password rotation was pending at archive time.
