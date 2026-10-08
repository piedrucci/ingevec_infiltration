# Category-specific causes

Each active cause is created with one category. A unique constraint on
`failure_cause_category_link.failure_cause_id` prevents multiple category links.
Items can have causes from several categories, and dashboard counts remain distinct
items per category. Retired shared causes remain inactive for auditability with no
category links or item assignments.

The split creates codes like `BROKEN_SEALS__WINDOWS` and
`BROKEN_SEALS__SHEET_METAL`. Display names stay the same; selectors already show
the category alongside the name. Qualified aliases such as
`Ventana · Sellos cortados` identify a specific cause. Bare shared names are
ambiguous and must be reviewed; inactive aliases are excluded from PDF matching
and item/cause import resolution.

## Deployment order

Deploy the updated API/worker code and command first. Stop ingestion and manual
cause edits during the operation. Copy the private completed `assignments.json`
into the API container. Keep reports on a mounted persistent private directory.
The database must be at `20261006_0022` before this operation.

```sh
python -m app.commands.split_category_causes /private/assignments.json \
  --dry-run --report /private/split-preview.json
python -m app.commands.split_category_causes /private/assignments.json \
  --apply --report /private/split-applied.json
alembic upgrade head
alembic current
python -m app.commands.import_category_causes /private/category_and_causes.json --dry-run
```

Use the updated `docs/category_and_causes.json` for the final dry-run. The split
already installs its required category links; applying the global mapping import
is unnecessary.

The split validates item IDs/public IDs, project, observation, the complete cause
set, provenance and the source category catalog. Production must pass its own
preview: differences from the development snapshot block apply and require a
fresh reviewed snapshot. Never bypass validation to force a development report
onto a different production database.

The command checks that the review covers every assignment to the shared causes,
blocks concurrent writes while applying, preserves unrelated item causes and
assignment provenance, synchronizes primary-cause pointers, and invalidates the
dashboard cache after commit. Document/item links and source Excel rows are not
modified. The private audit includes the original snapshot and decisions.

Apply is intentionally one-shot: a repeat fails with "already retired" rather
than replacing assignments again. Audit status `pending` means the process may
have been interrupted; inspect database state before retrying. Alembic downgrade
only removes the uniqueness constraint; it does not undo the data split. Restore
reviewed assignments only through a separately reviewed recovery operation.

After deployment, verify there are no shared category links or assignments to
inactive shared causes, every reviewed item has the selected destination codes,
primary pointers match assigned causes, and reconciled-item and PDF-link totals
are unchanged. Refresh open UI pages so their cause catalogs reload.
