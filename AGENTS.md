# Ingevec Postventa contributor guide

## Purpose

This repository contains the backend and administrative UI for Ingevec post-sale traceability. It ingests the `Año 2026` worksheet from controlled Excel uploads, preserves every source row for auditability, normalizes valid rows into the `app` PostgreSQL schema, processes PDF reports asynchronously, and exposes analytics through the API and Superset.

## Layout

- `apps/api/app/`: FastAPI application, SQLAlchemy models, authentication, import/document services, and workers.
- `apps/api/app/commands/`: reusable operational CLI commands for category/cause links, group/category links, and item/cause reassignment.
- `apps/api/migrations/`: Alembic migrations; migrations are the source of truth for deployed schema changes.
- `apps/api/tests/`: API and service tests.
- `apps/web/`: React/Vite administrative UI. It authenticates with Keycloak and calls the API through Vite's development `/v1` proxy or the configured production API URL.
- `infra/`: NATS, SeaweedFS, Keycloak, Superset, and reverse-proxy configuration.
- `docs/`: deployment and operational documentation, including the `category_and_causes.json` association mapping and database ERD.
- `compose*.yaml`, `Dockerfile`, `config/*.env.example`: local and production runtime configuration.
- `data/`: sample/source workbooks. Treat these as business data; do not overwrite them during automated work. Database dumps in the repository are also business data and must not be regenerated or replaced casually.

## Production deployment

- Production runs as a Docker Compose stack in Dokploy on the Hostinger VPS. GitHub is the deployment source; `compose.yaml` is combined with `compose.prod.yaml`. See `docs/deployment.md` for the deployment procedure and production service domains.
- The application database is Neon, not a database hosted on the VPS. Production credentials are stored in Dokploy environment variables; never add them to this file or Git.
- Operational JSON files are business data and are git-ignored. Keep them private and mount or copy them into the target API container before running an import command.
- VPS SSH connection details (host or alias, username, and remote paths) are not tracked in this repository. Obtain them from the authorized server configuration; do not infer or commit them.

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
- Each cause may link to only one category through `app.failure_cause_category_link` (unique `failure_cause_id`); keep this junction table. Items may have multiple causes from different categories. Retired shared causes are inactive and have no category links. Category-qualified aliases distinguish causes with the same display name. See `docs/cause-category-split.md` before applying migration `20261008_0023`.
- Failure-cause groups (`EJECUCION`, `PROPIETARIO`, `DISENO`) and categories are many-to-many through `app.failure_cause_category_group_link`; preserve Spanish accents in `display_name_es` labels and keep associations in this junction table.
- The reusable association importer is `python -m app.commands.import_category_causes <json-file>`. Run it with `--dry-run` first; it replaces all junction-table rows atomically, skips missing codes with warnings, and accepts inactive categories and causes.
- Group/category associations from the María Platias JSON use `python -m app.commands.import_group_categories <json-file>`. Run `--dry-run` first; this importer is add-only and idempotent, skips rows with missing groups, matches labels case/accent-insensitively while reporting normalized matches, and reports unmatched or ambiguous labels. It must not change item/cause or document/item associations.
- Cause reassignment from the María Platias JSON uses `python -m app.commands.preview_postventa_item_causes <json-file> --dry-run` followed by `--apply`. Apply revalidates inside a transaction, blocks concurrent edits to item/cause tables, atomically replaces all cause links, synchronizes the legacy primary-cause pointer, invalidates the dashboard cache, and does not change document/item associations. Ambiguous notes or unresolved cause labels block apply; unmatched source notes are reported and skipped, and matched items with no causes remain pending.
- Item notes match exactly after trimming outer whitespace; capitalization, prefixes, and additional text still matter. Cause labels resolve through normalized catalog names and aliases. Repeated JSON notes union their causes; a note matching multiple database items is accepted only when their source-row hashes are identical and repeated JSON rows have identical cause sets.
- Item reconciliation is derived from the presence of at least one `app.postventa_item_failure_cause` row. A global replacement makes every item without a planned cause link pending, including items absent from the JSON. An unmatched JSON note is a skipped source record, not a separate pending database item.
- Rebuilt cause links use `assignment_source=MIGRATED`, a new assignment timestamp, and no source document reference. Existing cause-link provenance is replaced; PDF links in `app.document_postventa_item` are preserved. The legacy `postventa_item.failure_cause_id` is the lowest selected cause ID, or null when no causes are assigned.
- Item pruning uses `python -m app.commands.prune_postventa_items <json-file> --dry-run --report <new-report> --cleaned-json <new-json>`, followed by `--apply --report <reviewed-report> --manifest <new-manifest>`. Notes match exactly after trimming; missing notes or multiple database matches block apply. Identical JSON duplicates are removed only in the separate cleaned copy. Apply rejects changed input/database state, deletes items absent from the allowlist, preserves source Excel data and retained associations, and deletes exclusively referenced documents and PDFs. PDFs referenced by retained item associations or cause provenance are preserved. Reports/manifests contain business data and must remain private, outside Git, on persistent storage. See `docs/item-pruning.md` for the maintenance window and `--resume-cleanup <manifest>` recovery procedure.

## Verification

From `apps/api`, install `requirements-dev.txt` and run `pytest`. For frontend changes, run `npm run build` from `apps/web`. For schema work, run `alembic upgrade head` against a disposable development database. For Compose changes, validate with the selected environment file and the appropriate overlays. For category/cause association changes, validate `docs/category_and_causes.json` with the importer dry-run before applying it to development or production. For group/category changes, validate `data/AGUAS_LLUVIAS_2026_MARIA_PLATIAS.json` with the group/category importer dry-run; review skipped rows and unmatched labels before applying it to development or production.

For item/cause reassignment, run the preview command with `--dry-run` in each target environment and review unmatched notes, ambiguous matches, unresolved causes, and projected reconciliation counts. Apply to development before production. After `--apply`, rerun the read-only preview and confirm current link/reconciled/pending counts match the plan. Matching fixes made manually in development must also be accounted for in production; a successful development preview does not establish that production notes or catalog labels match. JSON files must be mounted or copied into the target container before running the command.

## Current boundaries

- Only the `Año 2026` sheet is imported in v1.
- The PDF worker blocks on JetStream and does not query Neon while idle. The API publishes each upload event immediately after commit; do not schedule recurring outbox reconciliation in production because each run can wake Neon compute. Run `python -m app.worker.reconcile` manually only to recover pending outbox events after a broker interruption. Run it with `--scan-storage` only when PDFs were placed directly in the `incoming/` prefix; normal uploads go through the API.
- The processor uses native PDF extraction with bounded Spanish OCR fallback, controlled failure-cause aliases, and conservative matching. Confident matches move to `processed/`; uncertain or failed documents remain in review/error states, with private object storage as the source of truth.
- Dashboard aggregates are cached for five minutes by default and must be invalidated when imports, documents, or associations change.
