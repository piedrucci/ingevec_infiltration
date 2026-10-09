# API Backend Specification

## Purpose

Rules that humans and AI agents SHALL follow when creating or modifying code in `apps/api` (FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL on Neon), workers, and operational commands for Ingevec Postventa post-sale traceability. Operational runbooks (one-time data operations, deployment) live in `docs/` and `AGENTS.md`; this spec holds the rules that apply to every implementation.

## Requirements

### Requirement: Code layout
- Routes in `app/` route modules SHALL stay thin: validation, auth dependency, call into a service.
- Workbook parsing/normalization and business logic SHALL live in `app/services/`.
- Persistence SHALL use the database session supplied by the route or worker.
- Reusable operational CLI commands SHALL live in `app/commands/`.
- Models SHALL use SQLAlchemy 2.x typed mappings (Python 3.12).

#### Scenario: New endpoint
- **WHEN** an agent adds an endpoint
- **THEN** the route only handles HTTP concerns and delegates to a function in `app/services/`
- **AND** a test is added under `apps/api/tests/`

### Requirement: Authentication defaults to deny
Authentication and authorization SHALL deny access unless the request is authenticated and authorized.

#### Scenario: Administrative endpoints
- **WHEN** an endpoint ingests data or mutates administrative state (imports, uploads, associations)
- **THEN** it uses the `require_admin` dependency
- **AND** an agent never removes or weakens it

### Requirement: Schema changes use Alembic migrations
Database schema changes SHALL be represented by Alembic migrations.

#### Scenario: Changing the schema
- **WHEN** a model or database object changes
- **THEN** a new Alembic migration is added in `apps/api/migrations/`
- **AND** an already-applied migration is never edited in a deployed environment
- **AND** `alembic upgrade head` is verified against a disposable development database

### Requirement: Schema changes update the ERD
Whenever the database schema is changed, the database ERD in `docs/database-erd.md` SHALL be updated to reflect the resulting schema.

#### Scenario: Updating the schema diagram
- **WHEN** a database schema change is made, including adding, changing, or removing a table, column, constraint, or relationship
- **THEN** `docs/database-erd.md` is updated in the same change to match the resulting schema
- **AND** its documented Alembic revision is updated when the schema change adds a new migration

### Requirement: Schema changes validate data-fetching queries
When a database schema change can affect how application data is fetched, all relevant data-fetching queries SHALL be reviewed, adjusted to match the resulting schema, and validated against it.

#### Scenario: Reviewing queries after a schema change
- **WHEN** a table, column, constraint, or relationship used by a data-fetching query is added, changed, or removed
- **THEN** the affected API, worker, analytics, and operational queries are reviewed
- **AND** stale references are updated or removed
- **AND** the affected queries are exercised against a database at the target migration revision

#### Scenario: Version table
- **WHEN** migration contexts are configured
- **THEN** `version_table_schema="public"` is set in both online and offline contexts, so `search_path=app` cannot hide `public.alembic_version`
- **AND** if Alembic tries the initial migration on an existing database, the agent inspects the version table and connection instead of stamping a revision to bypass it

### Requirement: Source-row provenance
Excel source-row provenance SHALL be preserved during ingestion and normalization.

#### Scenario: Excel ingestion
- **WHEN** a workbook is imported
- **THEN** every source row is preserved in `ExcelSourceRow`
- **AND** `raw_cells` is never updated or discarded
- **AND** derived records remain linked through `source_row_id`
- **AND** only the `Año 2026` sheet is imported

### Requirement: Idempotent ingestion
Excel and PDF ingestion SHALL use SHA-256 duplicate detection to remain idempotent.

#### Scenario: Re-uploading the same file
- **WHEN** an Excel file or PDF with an already-seen SHA-256 is uploaded
- **THEN** duplicate detection prevents re-ingestion
- **AND** changes to ingestion code preserve this behavior

### Requirement: Postventa items exclude item-type catalog data
The `app.item_type` table and `app.postventa_item.item_type_id` relationship SHALL NOT exist. Original workbook cells SHALL remain preserved in `app.excel_source_row.raw_cells` for provenance.

#### Scenario: Import workbook rows
- **WHEN** workbook rows are normalized into postventa items
- **THEN** item type is not required to create the normalized item
- **AND** the original source cells remain unchanged

### Requirement: Cause and category integrity
Cause/category links SHALL preserve the following invariants:

- Each cause SHALL link to at most one category through `app.failure_cause_category_link` (unique `failure_cause_id`); this junction table is kept.
- Items MAY have multiple causes from different categories.
- Retired shared causes SHALL be inactive with no category links; category-qualified aliases distinguish causes with the same display name.

#### Scenario: Category-qualified cause
- **WHEN** a cause is assigned to a category
- **THEN** it has no more than one category link
- **AND** an item can still have separate causes from multiple categories

### Requirement: Cause group/category associations
Groups and categories SHALL have a many-to-many relationship through `app.failure_cause_category_group_link`. Spanish accents in `display_name_es` labels SHALL be preserved.

#### Scenario: Group and category links
- **WHEN** a group is associated with one or more categories
- **THEN** the associations are represented by junction-table rows
- **AND** category labels retain their Spanish accents

### Requirement: Dashboard category totals
Dashboard category totals SHALL count each item at most once per category.

#### Scenario: Item has causes in a category
- **WHEN** dashboard item totals are grouped by failure-cause category
- **THEN** an item is counted at most once in each category, even when it has multiple causes linked to that category
- **AND** an item MAY contribute once to each of multiple categories when its causes span those categories

### Requirement: Project geography
Project and location geography SHALL support incomplete source data.

- Project address, latitude, and longitude SHALL be nullable to support records without confirmed map details.
- A location MAY have a nullable `geographic_zone` string.

#### Scenario: Missing map details
- **WHEN** a project has no verified map address or coordinates
- **THEN** its address, latitude, and longitude can remain null

### Requirement: Subcontractor relationships
- Each subcontractor SHALL reference exactly one speciality.
- Projects and subcontractors SHALL have a many-to-many relationship through `app.project_subcontractor`.
- Specialities and subcontractor/project associations are maintained directly in the database; the administrative UI SHALL NOT provide CRUD or assignment workflows for them.
- The subcontractor dashboard SHALL display each subcontractor's speciality and associated-project count, ordered by project count descending.

#### Scenario: Shared subcontractor or project
- **WHEN** a subcontractor is associated with multiple projects, or a project with multiple subcontractors
- **THEN** each association is stored as a separate `app.project_subcontractor` row
- **AND** the speciality remains a single value on the subcontractor

### Requirement: Item reconciliation
Item reconciliation SHALL be derived from the item's cause-assignment links.

#### Scenario: Item reconciliation
- **WHEN** reconciliation status is computed
- **THEN** an item is reconciled if and only if it has at least one `app.postventa_item_failure_cause` row
- **AND** the legacy `postventa_item.failure_cause_id` is the lowest selected cause ID, or null when none are assigned

### Requirement: Operational commands are safe by default
Commands that mutate business data SHALL default to a non-mutating preview and require an explicit `--apply` (or an equally clear confirmation flag). The preview SHALL report the affected records and material validation issues before changes are committed.

#### Scenario: Data-changing command
- **WHEN** an agent adds or changes a command that mutates business data
- **THEN** it defaults to preview and requires an explicit apply action
- **AND** changes are committed transactionally
- **AND** preview/apply workflows that rely on a reviewed snapshot revalidate the input and relevant database state during apply, and reject stale reviews
- **AND** any generated report or recovery manifest is written to a new private path outside Git; operational reports containing business data are kept on private persistent storage
- **AND** cached dashboard data is invalidated after a successful change that affects dashboard results

#### Scenario: One-time operations
- **WHEN** a task touches the category-specific cause split or item pruning
- **THEN** the agent follows `docs/cause-category-split.md` or `docs/item-pruning.md`
- **AND** never applies migration `20261008_0023` before the split, repeats a successful split, or runs an applying `import_category_causes` after the split without a separately reviewed change

### Requirement: Dashboard cache
Cached dashboard aggregates SHALL be invalidated after changes that affect their results.

#### Scenario: Data changes
- **WHEN** imports, documents, or associations change
- **THEN** cached dashboard aggregates (5 minute default) are invalidated

### Requirement: PDF pipeline and worker
- The API SHALL publish each upload event to NATS JetStream immediately after commit.
- The worker SHALL block on JetStream and SHALL NOT query Neon while idle.
- Recurring outbox reconciliation SHALL NOT be scheduled in production; `python -m app.worker.reconcile` is manual only (`--scan-storage` only for PDFs placed directly in `incoming/`).
- Uploaded documents and source workbooks SHALL stay in private SeaweedFS storage, never exposed through a public path.

#### Scenario: PDF upload processing
- **WHEN** a PDF upload is committed
- **THEN** the API publishes its processing event after the database commit
- **AND** the worker waits for events without polling Neon while idle

### Requirement: Secrets and configuration
Secrets SHALL remain outside source control, and new required settings SHALL be documented in both environment examples.

#### Scenario: New setting
- **WHEN** a required setting is added
- **THEN** both `config/*.env.example` files are updated
- **AND** no secret, credential, or Neon connection string is committed or added to `AGENTS.md`

### Requirement: Business data is protected
Business source data, database dumps, and operational data files SHALL be handled as private, immutable inputs unless the task explicitly calls for an approved transformation.

#### Scenario: Data files
- **WHEN** an agent works near `data/`, database dumps, or operational JSON files
- **THEN** it does not overwrite, regenerate, or commit them
- **AND** tests use synthetic fixtures

### Requirement: Verification
Backend and deployment changes SHALL be verified with the applicable repository checks.

#### Scenario: Before finishing
- **WHEN** an agent finishes a backend change
- **THEN** `pytest` passes from `apps/api` (with `requirements-dev.txt` installed)
- **AND** Compose changes are validated with the selected env file and overlays
