# Pruning items using the María Platias JSON

The command retains one item per unique, trimmed JSON note and removes all other
items from `app.postventa_item`. The current source has 681 unique notes; the
command derives its target from the supplied file rather than hardcoding 681.
It does not create missing items or select among duplicate database matches.

Use a private, persistent operations directory mounted at the same container
path for preview, apply, and recovery. The examples use `/ops`. Reports contain
item records, document metadata, dependent links, and outbox records; they are
recovery artifacts, not public logs. Store them outside Git, with the database
backup and recoverable copies of PDFs selected for deletion. Outputs are created
with mode 0600 and existing files are never overwritten.

## Preview

Copy the latest JSON into the operations directory. Run in development first:

```bash
python -m app.commands.prune_postventa_items \
  /ops/AGUAS_LLUVIAS_2026_MARIA_PLATIAS.json --dry-run \
  --report /ops/prune-preview.json \
  --cleaned-json /ops/AGUAS_LLUVIAS_2026_MARIA_PLATIAS_CLEANED.json
```

The source remains intact. The cleaned JSON retains the first completely
identical duplicate row; conflicting rows with the same trimmed note are
rejected. Blank notes and empty input are rejected. Matching is case sensitive,
including accents, prefixes, and internal whitespace.

Review `plan` in the report: retained/deleted item IDs, missing/ambiguous notes,
affected cause and PDF links, exclusive/shared documents, storage keys, and
projected reconciliation counts. The snapshot supplies notes and complete
records for each ID. `apply_ready` must be true. Resolve matching discrepancies
and generate a fresh report with new output filenames if anything changes.

The command never deletes unrelated documents. A PDF associated with a deleted
item is preserved when any retained item references it through a PDF association
or a cause's `source_document_id`. Cause links belonging to retained items and
their primary-cause values are not rebuilt.

## Apply

Before apply, obtain a database backup and recoverable copies/snapshot of the
selected PDFs. Pause imports, uploads, manual association edits, the PDF worker,
and scheduled reconciliation until storage cleanup is complete. Run the command
in a maintenance container sharing the target environment and the persistent
operations mount; an ephemeral container filesystem is not sufficient for the
recovery manifest. Review again if the database changed since preview.

```bash
python -m app.commands.prune_postventa_items \
  /ops/AGUAS_LLUVIAS_2026_MARIA_PLATIAS.json --apply \
  --report /ops/prune-preview.json \
  --manifest /ops/prune-recovery.json
```

Apply validates the source hash, cleaned JSON, database/storage identity, full
database snapshot, and deletion plan under table locks. It writes a recovery
manifest before committing any deletion. Item, cause-link, PDF-link, document,
and dependent outbox deletion occurs within one database transaction; source
Excel rows, their raw cells and normalization metadata, imports, and catalogs
are preserved. The final item count and trimmed note set must equal the cleaned
JSON before commit. Dashboard caches are invalidated after commit.

Storage cleanup follows the database commit. Each selected object's content
hash must match the recorded document hash. Referenced or overwritten objects
are refused; already absent objects count as cleaned up. The command uses each
document's recorded bucket, not the configured default bucket. Each result is
persisted in the manifest.

## Recover and verify

PostgreSQL deletion and S3 deletion cannot be atomic together. A storage failure
does not undo committed database changes. Keep the recovery manifest and retry:

```bash
python -m app.commands.prune_postventa_items \
  --resume-cleanup /ops/prune-recovery.json
```

Resume checks the target environment and confirms selected database records are
gone before deleting storage objects. A manifest left in `prepared` after a
database rollback cannot delete PDFs for records still present. A crash after
commit but before the manifest phase update can still be recovered. Do not
resume uploads or reconciliation while cleanup is pending: an incoming object
without its document record could otherwise be registered again.

The manifest's `phase` must finish at `complete`. Run a new dry-run with new
report and cleaned-output filenames. It must show the exact target count,
`apply_ready=true`, and zero item/document deletions. Verify retained PDF access
and dashboard reconciliation totals before ending the maintenance window.
Restore from the database and storage backups if rollback is needed after
commit; the manifest supplies record-level details but is not a full database
or PDF backup.

Repeat preview and review independently in production. Development IDs and
counts are not an authorization to delete production records; production's
reviewed report determines its deletion set. This command requires no schema
migration or API/UI changes. It prunes current data and does not enforce an
ongoing allowlist against future imports.
