# Superset analytics datasets

The Superset provisioner registers three read-only datasets from the `analytics`
schema in the `Ingevec Postventa Analytics` database:

| Dataset | Grain | Intended use |
| --- | --- | --- |
| `analytics.postventa_item_dashboard` | Item × associated document (currently one row per item) | Overall volume, reconciliation status, project/division summaries, document status |
| `analytics.postventa_item_cause_dashboard` | Item × assigned cause × category × group | Cause, category, and group analysis |
| `analytics.postventa_item_cause_pareto` | Item × assigned cause × category × group | Filter-aware Pareto charts by cause |

The item dataset can produce multiple rows for an item if multiple documents are
associated later. The cause dataset expands rows across the many-to-many cause,
category, and group links. Therefore, do not use raw row counts as item counts.

Recommended measures:

- Total items: `COUNT(DISTINCT postventa_item_public_id)` on either dataset.
- Reconciled items: distinct item count filtered by `esta_conciliado = true` on
  `postventa_item_dashboard`.
- Pending items: distinct item count filtered by `esta_conciliado = false` on
  `postventa_item_dashboard`.
- Item/cause pairs: `COUNT(DISTINCT (postventa_item_public_id,
  codigo_causa_falla))` on the cause dataset. This avoids counting the same
  item/cause pair repeatedly when its cause belongs to multiple categories or
  groups.
- Pareto charts: use `items_per_cause` grouped by `causa_falla`, sorted by that
  metric descending, and add `cumulative_share` as a second metric. It reports
  the cumulative share of item/cause pairs, rather than the share of unique
  items (an item assigned multiple causes contributes to each cause). The window
  calculation runs after dashboard filters, so project, date, category, group,
  and division scope selections are reflected in the cumulative percentage.

The provisioner registers these as reusable dataset metrics. Keycloak users
with `superset_viewer` receive the custom read-only `Ingevec Viewer` role.
Dashboard authors should receive `superset_dashboard_builder`, which maps to
`Ingevec Dashboard Builder`: it adds chart/dashboard authoring and Explore
permissions without SQL Lab access. Both roles receive access only to the three
curated datasets, and all are subject to project/division row-level scope.
`superset_admin` remains the unrestricted Superset administrator role.

An item can belong to more than one group through its categories, so group
breakdowns are non-additive: summing group totals may exceed the overall number
of distinct items. Cause/category/group labels are nullable where catalog links
have not been assigned; keep those rows visible when auditing incomplete
classification, or explicitly exclude null labels for finalized reporting.

All three datasets use the same server-side division/project scope filters for
Keycloak-backed viewers. The database connection uses the read-only
`superset_reader` role. The viewer role receives datasource access to these
curated datasets; dashboard authoring remains an administrator responsibility.
