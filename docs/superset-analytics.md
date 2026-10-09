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

## Embedding Dashboard Principal in the admin application

The React app exposes the published Superset dashboard at `/analytics` through the official `@superset-ui/embedded-sdk` 0.4.0. Embedding is opt-in (`SUPERSET_EMBEDDING_ENABLED=false` by default). The API issues short-lived, dashboard-only guest tokens; it never accepts a dashboard ID or row scope from the browser. The guest token expires after five minutes and the SDK requests a new one through the authenticated API client. Guest-token responses are not cacheable.

The user needs both the existing Keycloak `admin` application role and one analytics realm role: `superset_admin`, `superset_viewer`, or `superset_dashboard_builder`. An app administrator without an analytics role is denied. Only `superset_admin` receives global analytics scope. Viewer and builder tokens receive the union of their `/superset/division/<numeric-id>` and `/superset/project/<project-id>` groups. Missing or malformed scope fails closed. The same global row rule is attached to all three curated analytics views, which expose `division_manager_id` and `numero_obra`; Superset's guest security hook denies guests on uncurated datasets and when an applicable rule is missing.

### Configure an environment

1. In the Keycloak `ingevec-web` client, add the full-path group-membership mapper named `ingevec analytics scope groups`. The realm JSON templates define this mapper for new local realms. Existing Keycloak clients do not gain a mapper just because the realm import file changed; update the live client and have affected users sign out and sign in again so their access tokens contain `groups`.
2. Generate a private, random `SUPERSET_GUEST_TOKEN_JWT_SECRET` with at least 32 characters. Set the same value only on the Superset service. Set a dedicated, strong password for `SUPERSET_EMBED_SERVICE_USERNAME` / `SUPERSET_EMBED_SERVICE_PASSWORD` in the API and Superset provisioner environment. The provisioner creates a database-authenticated issuer account with only the `can_read` permission needed for CSRF retrieval and `can_grant_guest_token` on `SecurityRestApi`; it also provisions the read-only `Ingevec Embedded Viewer` role for the three curated datasets. Never reuse the Superset bootstrap admin account.
3. Set `SUPERSET_PUBLIC_URL` to the browser-facing Superset origin and `SUPERSET_INTERNAL_URL` to the Compose service URL (normally `http://superset:8088`). Set `SUPERSET_EMBED_ALLOWED_ORIGINS` to the exact React app origin (for local Vite, normally `http://localhost:5173`; production, `https://app.capix.cloud`). These origins drive both Superset's iframe CSP and its embedded-dashboard referrer check.
4. In Superset, open Dashboard Principal's **Edit dashboard** menu, choose **Embed**, enable embedding, and allow only the same app origin. Copy the generated embedded dashboard UUID, which differs from the numeric dashboard ID and ordinary dashboard UUID, to `SUPERSET_EMBEDDED_DASHBOARD_UUID` for that environment.
5. Run the `superset-provisioner` once with the intended private environment file, recreate Superset so it loads its signing secret and CSP, then start/redeploy the API with embedding enabled. The deployment starts with embedding disabled until these steps are complete. Do not put any of these secrets in Vite variables.

The API exposes authenticated `GET /v1/analytics/dashboard` metadata and `POST /v1/analytics/guest-token` with no request body. Both require `admin` plus an analytics role. A disabled integration returns `{ "enabled": false }` from the metadata endpoint; token issuance returns a sanitized 503 if configuration or Superset is unavailable. Requests containing query parameters or a body are rejected. The browser should use the SDK token callback for every initial mount and refresh, not store tokens in local storage or query caches.

Before enabling production, test each scoped account against the same filters in Superset and the embedded UI: separate project scopes, a division scope, a user with both scope types, analytics admin, missing scope, expired/forged tokens, unrelated dashboard IDs, uncurated datasets, native filters, and exports. Verify the actual embedded route response carries `Content-Security-Policy: frame-ancestors` for only the configured origin and does not have a conflicting `X-Frame-Options` header. Keep production embedding disabled until these checks pass. To roll back, set `SUPERSET_EMBEDDING_ENABLED=false` and redeploy; revoke the issuer password or rotate the guest signing secret if already-issued guest tokens must be invalidated immediately.
