# Ingevec Postventa contributor guide

## Purpose

This repository contains the backend and administrative UI for Ingevec post-sale traceability. It ingests the `Año 2026` worksheet from controlled Excel uploads, preserves every source row for auditability, normalizes valid rows into the `app` PostgreSQL schema, processes PDF reports asynchronously, and exposes analytics through the API and Superset.

## Layout

- `apps/api/app/`: FastAPI application, SQLAlchemy models, authentication, import/document services, and workers.
- `apps/api/migrations/`: Alembic migrations; migrations are the source of truth for deployed schema changes.
- `apps/api/tests/`: API and service tests.
- `apps/web/`: React/Vite administrative UI. It authenticates with Keycloak and calls the API through Vite's development `/v1` proxy or the configured production API URL.
- `infra/`: NATS, SeaweedFS, Keycloak, Superset, and reverse-proxy configuration.
- `docs/`: deployment and operational documentation.
- `compose*.yaml`, `Dockerfile`, `config/*.env.example`: local and production runtime configuration.
- `data/`: sample/source workbooks. Treat these as business data; do not overwrite them during automated work. Database dumps in the repository are also business data and must not be regenerated or replaced casually.

## Working conventions

- Python 3.12, FastAPI, SQLAlchemy 2.x typed mappings, Alembic, and PostgreSQL/Neon for the application database.
- React 19, TypeScript, Vite, React Query, React Router, and `keycloak-js` for the administrative UI.
- NATS JetStream carries PDF events; Redis caches dashboard summaries; SeaweedFS provides private S3-compatible object storage; Superset reads the published analytics views through its restricted reader connection.
- Keep route modules thin. Put workbook parsing/normalization in `app/services/` and persistence in the database session supplied by the route or worker.
- Preserve source-row provenance. Do not update or discard `ExcelSourceRow.raw_cells`; derived records should remain linked through `source_row_id`.
- Excel imports and PDF uploads are idempotent by SHA-256. Preserve duplicate detection when changing ingestion.
- Authentication defaults to deny. Administrative ingestion endpoints must retain `require_admin`.
- Add a migration for every database schema change. Do not edit an already-applied migration in a deployed environment.
- Keep environment secrets out of Git. Update both environment examples whenever a required setting is added.
- Keep uploaded documents and source workbooks in private object storage. Do not expose SeaweedFS objects through a public path or commit storage credentials.

## Verification

From `apps/api`, install `requirements-dev.txt` and run `pytest`. For frontend changes, run `npm run build` from `apps/web`. For schema work, run `alembic upgrade head` against a disposable development database. For Compose changes, validate with the selected environment file and the appropriate overlays.

## Current boundaries

- Only the `Año 2026` sheet is imported in v1.
- The PDF worker consumes JetStream events and publishes through a transactional outbox. It does not poll object storage. Run `python -m app.worker.reconcile --scan-storage` only when PDFs were placed directly in the `incoming/` prefix; normal uploads go through the API. Production schedules outbox reconciliation externally.
- The processor uses native PDF extraction with bounded Spanish OCR fallback, controlled failure-cause aliases, and conservative matching. Confident matches move to `processed/`; uncertain or failed documents remain in review/error states, with private object storage as the source of truth.
- Dashboard aggregates are cached for five minutes by default and must be invalidated when imports, documents, or associations change.
