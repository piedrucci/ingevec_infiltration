# Superset analytics datasets

The Superset provisioner registers four read-only datasets from the `analytics`
schema in the `Ingevec Postventa Analytics` database:

| Dataset | Grain | Intended use |
| --- | --- | --- |
| `analytics.postventa_item_dashboard` | Item × associated document (currently one row per item) | Overall volume, reconciliation status, project/division summaries, document status |
| `analytics.postventa_item_cause_dashboard` | Item × assigned cause (× category groups only for unassigned causes) | Cause, category, and group analysis |
| `analytics.postventa_item_cause_pareto` | Item × assigned cause (× category groups only for unassigned causes) | Filter-aware Pareto charts by cause |
| `analytics.postventa_item_subcontractor_dashboard` | Item × assigned cause × credited subcontractor, plus one row per project assignment without matching items | Subcontractor rankings and per-subcontractor project lists |

The item dataset can produce multiple rows for an item if multiple documents are
associated later. The cause datasets have one row per item and assigned cause when
the cause has a group (migration `20261019_0025`); a cause without a group still
expands across every group of its category. Therefore, do not use raw row counts
as item counts.

The subcontractor dataset (migration `20261020_0028`) credits an item-cause to the
item's project subcontractor whose speciality matches the cause's category
(`failure_cause_category.speciality_id`: Ventana, Fachada, Hojalateria,
Impermeabilización; Instalaciones → Sanitario; Desnivel, Descarga and Otro have
none). Item-causes without a speciality or a matching subcontractor keep null
`especialidad`/`subcontratista` values; filter `subcontratista IS NOT NULL` for
rankings. Each project assignment with no matching item-causes adds one row with
null item and cause columns, so a subcontractor's project list shows it with 0
items; a group, category, cause or date filter removes those rows. Use its
`items_distinct` metric (`COUNT(DISTINCT postventa_item_public_id)`); two
subcontractors of the same speciality on one project are both credited. For
cascading filters, make the `subcontratista` native filter depend on the
`especialidad` filter.

Jinja templating is enabled (`ENABLE_TEMPLATE_PROCESSING`). Superset cannot hide
a chart conditionally; to keep a chart empty until a dashboard filter has a
value, add a Custom SQL filter such as
`{{ '1 = 1' if filter_values('proyecto') else '1 = 0' }}` (used by the
per-project subcontractor table). Only chart authors write SQL, and row-level
security still applies to templated queries.

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
permissions without SQL Lab access. Both roles receive access only to the four
curated datasets, and all are subject to project/division row-level scope.
`superset_admin` remains the unrestricted Superset administrator role.

An item can belong to more than one group through causes of different groups (or
through an unassigned cause's category), so group breakdowns are non-additive: summing group totals may exceed the overall number
of distinct items. Cause/category/group labels are nullable where catalog links
have not been assigned; keep those rows visible when auditing incomplete
classification, or explicitly exclude null labels for finalized reporting.

All four datasets use the same server-side division/project scope filters for
Keycloak-backed viewers. The database connection uses the read-only
`superset_reader` role. The viewer role receives datasource access to these
curated datasets; dashboard authoring remains an administrator responsibility.

## Checking datasets after analytics migrations

After a migration that changes an `analytics` view, run the read-only checker inside the Superset container:

```sh
docker exec -w /app <superset-container> python /app/pythonpath/ingevec/check_analytics.py
```

Through the `superset_reader` connection it compares each dataset's stored columns with the live view, runs every dataset metric, executes every saved chart query, and flags chart or dashboard references to retired values (split cause codes, renamed causes, removed columns; pass other values as arguments). It ends with `OK: no problems found` or `PROBLEMS: N` (exit code 1). Charts never saved in Explore are reported as not executed. It runs as an Admin user, so row-level scope must still be checked with a non-admin viewer.

Migration `20261019_0025` keeps the cause views' columns, so datasets and saved charts need no changes. Group breakdowns on the cause datasets now count an item only in the groups of its own causes (previously in every group of the cause's category), so "Items por grupo" values drop for groups that only shared categories. Use the distinct-item metrics, not `count`, for item totals.

`infra/superset` is bind-mounted from the deployment checkout. Dokploy replaces the checkout on each deploy, and a Superset container that is not recreated keeps the old, deleted directory: the running server still works with the config it loaded at start, but new processes (this checker, `superset` CLI commands) cannot find `superset_config.py`. Restart the Superset container after a deploy (`docker restart <superset-container>`, about a minute of BI downtime) and confirm `ls /app/pythonpath/ingevec/` lists the files. Until then, run the checker with a copied config: `docker cp` `superset_config.py` and `check_analytics.py` to `/tmp` and add `-e SUPERSET_CONFIG_PATH=/tmp/superset_config.py`.

## Project map

`analytics.postventa_item_dashboard` exposes `latitud`, `longitud` and `direccion` of each item's project (migration `20261020_0026`). After deploying, sync the dataset columns (Datasets → edit `postventa_item_dashboard` → Columns → **Sync columns from source**, or rerun `superset-provisioner`). For a marker map use **deck.gl Scatterplot** with `longitud`/`latitud` and point size `items_distinct`: points aggregate per project location, so marker size reflects distinct items. The base map in Superset 4.1.2 comes from Mapbox and requires `MAPBOX_API_KEY` on the Superset service (passed through `compose.yaml`; set it in the environment file or Dokploy, never in Git, and recreate Superset); without it markers render on an empty background. Use a Mapbox public token (`pk.`) restricted to the Superset URL. Coordinates and addresses are visible to every viewer within their row-level scope. deck.gl charts are legacy visualizations in 4.1.2 that load data through `/superset/explore_json/`; the provisioner grants `can_explore_json` to the viewer, builder and embedded roles (dataset access and row-level security still apply). Without it the map shows "Unexpected error" to everyone except admins, including the embedded `/analytics` view.

## Embedding Dashboard Principal in the admin application

The React app exposes the published Superset dashboard at `/analytics` through the official `@superset-ui/embedded-sdk` 0.4.0. Embedding is opt-in (`SUPERSET_EMBEDDING_ENABLED=false` by default). The API issues short-lived, dashboard-only guest tokens; it never accepts a dashboard ID or row scope from the browser. The guest token expires after five minutes and the SDK requests a new one through the authenticated API client. Guest-token responses are not cacheable.

The user needs both the existing Keycloak `admin` application role and one analytics realm role: `superset_admin`, `superset_viewer`, or `superset_dashboard_builder`. An app administrator without an analytics role is denied. Only `superset_admin` receives global analytics scope. Viewer and builder tokens receive the union of their `/superset/division/<numeric-id>` and `/superset/project/<project-id>` groups. Missing or malformed scope fails closed. The same global row rule is attached to all four curated analytics views, which expose `division_manager_id` and `numero_obra`; Superset's guest security hook denies guests on uncurated datasets and when an applicable rule is missing.

### Configure an environment

1. In the Keycloak `ingevec-web` client, add the full-path group-membership mapper named `ingevec analytics scope groups`. The realm JSON templates define this mapper for new local realms. Existing Keycloak clients do not gain a mapper just because the realm import file changed; update the live client and have affected users sign out and sign in again so their access tokens contain `groups`.
2. Generate a private, random `SUPERSET_GUEST_TOKEN_JWT_SECRET` with at least 32 characters. Set the same value only on the Superset service. Set a dedicated, strong password for `SUPERSET_EMBED_SERVICE_USERNAME` / `SUPERSET_EMBED_SERVICE_PASSWORD` in the API and Superset provisioner environment. The provisioner creates a database-authenticated issuer account with only the `can_read` permission needed for CSRF retrieval and `can_grant_guest_token` on `SecurityRestApi`; it also provisions the read-only `Ingevec Embedded Viewer` role for the four curated datasets. Never reuse the Superset bootstrap admin account.
3. Set `SUPERSET_PUBLIC_URL` to the browser-facing Superset origin and `SUPERSET_INTERNAL_URL` to the Compose service URL (normally `http://superset:8088`). Set `SUPERSET_EMBED_ALLOWED_ORIGINS` to the exact React app origin (for local Vite, normally `http://localhost:5173`; production, `https://app.capix.cloud`). These origins drive both Superset's iframe CSP and its embedded-dashboard referrer check.
4. In Superset, open Dashboard Principal's **Edit dashboard** menu, choose **Embed**, enable embedding, and allow only the same app origin. Copy the generated embedded dashboard UUID, which differs from the numeric dashboard ID and ordinary dashboard UUID, to `SUPERSET_EMBEDDED_DASHBOARD_UUID` for that environment.
5. Run the `superset-provisioner` once with the intended private environment file, recreate Superset so it loads its signing secret and CSP, then start/redeploy the API with embedding enabled. The deployment starts with embedding disabled until these steps are complete. Do not put any of these secrets in Vite variables.

The API exposes authenticated `GET /v1/analytics/dashboard` metadata and `POST /v1/analytics/guest-token` with no request body. Both require `admin` plus an analytics role. A disabled integration returns `{ "enabled": false }` from the metadata endpoint; token issuance returns a sanitized 503 if configuration or Superset is unavailable. Requests containing query parameters or a body are rejected. The browser should use the SDK token callback for every initial mount and refresh, not store tokens in local storage or query caches.

Before enabling production, test each scoped account against the same filters in Superset and the embedded UI: separate project scopes, a division scope, a user with both scope types, analytics admin, missing scope, expired/forged tokens, unrelated dashboard IDs, uncurated datasets, native filters, and exports. Verify the actual embedded route response carries `Content-Security-Policy: frame-ancestors` for only the configured origin and does not have a conflicting `X-Frame-Options` header. Keep production embedding disabled until these checks pass. To roll back, set `SUPERSET_EMBEDDING_ENABLED=false` and redeploy; revoke the issuer password or rotate the guest signing secret if already-issued guest tokens must be invalidated immediately.
