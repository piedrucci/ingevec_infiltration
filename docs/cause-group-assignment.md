# Cause group assignment

Each failure cause belongs to one category and at most one group (Ejecución, Propietario, Diseño).
Groups and categories stay many-to-many; `failure_cause_category_link.group_id` records the cause's
group, and a composite foreign key requires that group to contain the cause's category.

The groups come from the María Platias analysis in the source workbook. The database has no other
record of an item's group, so every environment needs the exported JSON.

## What the operation does

`app.commands.apply_cause_assignments` reads the exported JSON and the target database and plans:

- **Group assignment:** a cause used in a single group gets that group.
- **Split:** a cause used in several groups becomes one cause per group (`<CODE>__<GROUP_CODE>`,
  same name, group-qualified alias such as `Propietario · Ventana · Sellos cortados`). The original is
  retired (inactive, no category link), as in the category split. Item links move to the new cause
  and keep their original provenance.
- **New causes:** causes in the JSON but not in the catalog are created in their category and group.
- **Item causes:** for every item matched by exact trimmed notes (and `project_id`), the item's causes
  become exactly the JSON's. New links use `assignment_source=MIGRATED`. Items with no JSON causes
  become pending. Database items absent from the JSON are not modified.
- Legacy `postventa_item.failure_cause_id` becomes the lowest assigned cause ID.
- PDF/item links and Excel source rows are never modified. The dashboard cache is invalidated.

Apply is blocked by: notes matching several items, project mismatches, unknown groups or
categories, a group that does not contain the category, a cause used with and without a group, an
item outside the JSON that uses a cause that must be split, code/alias collisions, or any database
change since the reviewed dry-run.

PDF matching uses aliases of active causes. A PDF that names only a split cause's bare name no
longer matches automatically and goes to manual review.

## Procedure (development first, then production)

1. Deploy the code. Migration `20261019_0025` is additive and auto-applied; until the operation runs
   every cause is unassigned and analytics keep the previous category-derived groups.
2. Pause ingestion and manual cause edits.
3. Recovery points:
   - Neon: create a branch from the target branch (`development` or `production`) at its current
     head, e.g. `<branch>-before-cause-groups-<date>`. Never use "Reset from parent" on
     `development`: its parent is `production`.
   - Logical backup: `pg_dump` with a client matching the server major version, against the direct
     (non-pooler) endpoint, into a private directory outside Git:
     ```sh
     docker run --rm -e PGURL='<direct Neon URL>' -v "<private dir>":/backup postgres:18-alpine \
       pg_dump "$PGURL" --format=custom --compress=9 --file=/backup/infiltration.dump
     ```
4. Export the JSON from the reviewed workbook (never overwrites):
   ```sh
   python -m app.commands.export_cause_assignments <workbook.xlsx> --output <new.json>
   ```
   Contradictions (unresolved categories, disagreement with `IncidenciasCausas`, duplicate notes)
   abort without writing; fix the workbook and export again.
5. Copy the JSON privately into the target API container and run the dry-run:
   ```sh
   python -m app.commands.apply_cause_assignments <new.json> --dry-run --report <dry-run.json>
   ```
   Review `plan.blockers`, `plan.warnings` (unmatched notes, causes left without a group),
   `plan.normalized_matches`, `plan.creations`, `plan.retirements` and `plan.summary`.
   Production must pass its own dry-run; do not reuse a development report. Production also needs
   the development catalog fixes, e.g. `DANO_GORRO_CHINO` renamed to `Daños de gorro chino`.
6. Apply with the reviewed report:
   ```sh
   python -m app.commands.apply_cause_assignments <new.json> --apply \
     --reviewed-report <dry-run.json> --report <applied.json>
   ```
   Apply locks the cause and item tables, recomputes the plan and refuses if the database or plan
   differs from the reviewed dry-run.
7. Verify: a new dry-run shows no changes; the Grupos page shows different causes per group; no
   item links to retired causes; PDF/item link totals are unchanged.

Reports and dumps contain business data: keep them private, outside Git, on persistent storage.

## Rollback

```sh
python -m app.commands.apply_cause_assignments --rollback <applied.json> --report <rollback.json>
```

Restores item links (with original provenance), legacy pointers, groups and retired causes, and
deletes the created causes. It refuses if any affected item or cause changed after the apply; in
that case restore the Neon branch (or `pg_restore` the dump into a fresh branch first) instead.
