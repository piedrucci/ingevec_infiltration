# Ingevec Postventa API contributor guide

## Purpose

This repository contains the backend for Ingevec post-sale traceability. It ingests the `Año 2026` worksheet from controlled Excel uploads, preserves every source row for auditability, normalizes valid rows into the `app` PostgreSQL schema, and is designed to add asynchronous PDF processing and analytics.

## Layout

- `apps/api/app/`: FastAPI application, SQLAlchemy models, authentication, and services.
- `apps/api/migrations/`: Alembic migrations; migrations are the source of truth for deployed schema changes.
- `apps/api/tests/`: API and service tests.
- `apps/web/`: React/Vite administrative UI. It authenticates with Keycloak and calls the API through Vite's local `/v1` proxy.
- `compose*.yaml`, `Dockerfile`, `config/*.env.example`: local and production runtime configuration.
- `data/`: sample/source workbooks. Treat these as business data; do not overwrite them during automated work.

## Working conventions

- Python 3.12, FastAPI, SQLAlchemy 2.x typed mappings, Alembic, PostgreSQL/Neon.
- React, TypeScript, Vite, and `keycloak-js` for the administrative UI.
- Keep route modules thin. Put workbook parsing/normalization in `app/services/` and persistence in the database session supplied by the route or worker.
- Preserve source-row provenance. Do not update or discard `ExcelSourceRow.raw_cells`; derived records should remain linked through `source_row_id`.
- Excel imports are idempotent by SHA-256. Preserve that behavior when changing ingestion.
- Authentication defaults to deny. Administrative ingestion endpoints must retain `require_admin`.
- Add a migration for every database schema change. Do not edit an already-applied migration in a deployed environment.
- Keep environment secrets out of Git. Update both environment examples whenever a required setting is added.

## Verification

From `apps/api`, run `pytest`. For schema work, run `alembic upgrade head` against a disposable development database. For compose changes, validate with the selected environment file and the appropriate compose overlays.

## Current boundaries

- Only the `Año 2026` sheet is imported in v1.
- Uploaded documents and source workbooks belong in the private S3-compatible bucket, never in a public path.
- The PDF worker scans `incoming/` every 60 seconds, publishes through a transactional outbox, and consumes JetStream events. It moves confidently matched PDFs to `processed/`; uncertain matches go to `pending-review/`.
