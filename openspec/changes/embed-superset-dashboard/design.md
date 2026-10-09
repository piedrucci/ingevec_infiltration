# Design

## Context

See `proposal.md` for motivation. The React application is a Vite SPA with React Router, a global application `admin` gate in `App.tsx`, the shared authenticated `api.ts` client, and TanStack Query. FastAPI validates Keycloak signature, issuer, and API audience in `current_claims`; `require_admin` additionally checks application roles. The application administrator role and Superset's `superset_admin` analytics role are distinct.

Superset 4.1.2 is already deployed with authored charts, curated datasets, and a read-only Neon connection. `KeycloakSecurityManager.get_rls_filters` adds project/division predicates for direct Superset users; users without scopes receive `1 = 0`. The `/superset/project/<id>` and `/superset/division/<id>` group mapper currently exists only on `ingevec-superset`, not `ingevec-web`. The provisioner manages viewer and builder permissions. Superset metadata persists independently of application migrations.

Observed 4.1.2 upstream behavior: guest JWT validation creates a distinct guest principal; guest RLS rules are retrieved separately from ordinary role RLS and included in cache keys. The embedded view checks the request referrer against configured origins. The SDK mounts the iframe and obtains renewed guest tokens through its callback.

References, pinned to the deployed server version:
- [SDK documentation](https://github.com/apache/superset/blob/4.1.2/superset-embedded-sdk/README.md)
- [Guest authentication and RLS implementation](https://github.com/apache/superset/blob/4.1.2/superset/security/manager.py)
- [Embedded view origin validation](https://github.com/apache/superset/blob/4.1.2/superset/embedded/view.py)

## Goals / Non-Goals

**Goals:** Integrate one existing dashboard into the administrative application; provide explicit authorization parity with direct Superset access; support local development followed by a controlled production rollout.

**Non-Goals:** Opening the admin application to analytics-only accounts, anonymous analytics access, chart authoring in the embedded page, dashboard import automation, or modifying application schemas/views. The root dashboard remains the existing API-driven screen.

## Decisions

### 1. Add a dedicated analytics route

Use `/analytics` with navigation label `Analítica`. Compose feature-local `AnalyticsPage`, `EmbeddedDashboard`, query/mutation hooks, types, and a lifecycle hook under `features/analytics/`. Use shadcn components for surrounding loading/error/retry UI, Tailwind for the host container and iframe sizing, and Spanish messages. Preserve the current `isAdmin()` gate. Any additional UI entitlement check belongs in the shared auth module; components never inspect raw Keycloak tokens.

This keeps the existing root dashboard accessible and gives the embedded view enough responsive space. Replacing `/` would remove the current operational summaries and is outside this proposal.

### 2. Use the official SDK with a server-side token broker

Install and pin a compatible `@superset-ui/embedded-sdk` release using pnpm after confirming its refresh/unmount APIs against Superset 4.1.2. Use the embedded UUID produced by Superset's embed settings, not the numeric dashboard ID or ordinary dashboard UUID.

Proposed API contract:
- `GET /v1/analytics/dashboard`: authorized metadata (`embedded_dashboard_uuid`, `superset_public_url`, title); no secret or guest token. TanStack Query caches this metadata per session.
- `POST /v1/analytics/guest-token`: accepts no access-selection input; returns a fresh token and expiry for the single configured dashboard. Use the shared authenticated client and a TanStack mutation on every SDK token callback. Reset mutation data on cleanup and avoid persistent cache adapters for credentials.
- Both routes require `require_admin` plus an analytics-entitlement dependency; invalid authentication yields 401, insufficient role/scope 403, disabled/incomplete configuration or an upstream outage a sanitized 503. Guest-token responses send `Cache-Control: no-store`.

A thin route calls `app/services/superset_embedding.py`. The service signs no tokens itself: it authenticates to Superset's internal API as a dedicated database-authenticated service account and requests `/api/v1/security/guest_token/`. Give that account only token issuance and any reads required by 4.1.2's endpoint checks; verify the minimum permission set locally. Do not reuse the bootstrap administrator password. Bound request timeouts, reuse a service login token in process memory until expiry, retry authentication once on an expired issuer session, and avoid logging token bodies or credentials. The browser receives only short-lived dashboard-scoped guest tokens.

Direct iframe/SSO was considered, but relies on Superset browser sessions and iframe cookie behavior. Sharing a JWT signing secret with the API was considered, but grants the API general signing authority and couples it to token format. The broker uses Superset's native issuance and validation.

### 3. Translate verified claims into analytics scope

Add a groups protocol mapper to `ingevec-web` in both realm templates and document the corresponding update for already-running Keycloak realms. Realm reimport alone does not establish that an existing deployed client changed. New access tokens must contain full-path groups; sign out/in or renew sessions after the mapper change.

Require an analytics realm role: `superset_admin`, `superset_viewer`, or `superset_dashboard_builder`, in addition to the existing application admin role. A plain application admin receives no implied analytics access. Only verified `superset_admin` receives the explicit global guest clause `1 = 1`. Viewer/builder users receive one parenthesized OR clause combining their valid division and project scopes, matching existing direct Superset union semantics.

Use the existing scope vocabulary: numeric division IDs and conservative alphanumeric/underscore/hyphen project IDs. Reject malformed relevant groups; unrelated groups grant no scope. Validate claim shapes, deduplicate/sort identifiers, bound scope counts/token sizes, and fail closed when scope is empty or too large. No request field may select a role, dashboard, or SQL predicate. Apply one global guest row rule to the three curated datasets because all expose `division_manager_id` and `numero_obra`; verify those columns against the deployed views.

### 4. Preserve direct-user RLS and require guest RLS

Configure the custom security manager whenever embedding is enabled, including local environments without OIDC configured. On the three curated datasets, validated native guest principals must carry a nonempty applicable global RLS clause; otherwise append denial. Valid guests retain native role/base restrictions and the native guest-token filters, without the additional Keycloak missing-role `1 = 0`. Guests receive denial on uncurated datasets in this integration. Direct Keycloak users follow the existing role-based logic unchanged.

This narrowly handles the guest principal after Superset validates JWT signature, audience, and expiration. It must never trust a browser header, username, or claimed scope as proof of guest authentication. Test query scope and native RLS cache keys to prevent cross-user cached results. Preserve ordinary anonymous denial.

Provision a separate `Ingevec Embedded Viewer` guest role with only the endpoint permissions needed for rendering/filtering the configured dashboard. Prefer Superset's native dashboard-scoped guest resource checks over general dataset grants; verify 4.1.2 behavior locally before finalizing the exact minimal permission list. Do not alter `Public`, clone unrestricted Gamma/Admin permissions, or grant SQL Lab/write access. Add idempotent provisioning for the issuer account and guest role without resetting existing authored assets or viewer/builder roles.

### 5. Configure environments explicitly

Proposed settings (document in both environment examples and wire into appropriate services):
- `SUPERSET_EMBEDDING_ENABLED`: opt-in, default false for existing deployments.
- `SUPERSET_PUBLIC_URL`: browser origin, e.g. local `http://localhost:8088`, production `https://bi.capix.cloud`.
- `SUPERSET_INTERNAL_URL`: API-to-Superset service URL, normally `http://superset:8088`.
- `SUPERSET_EMBEDDED_DASHBOARD_UUID`: per-environment embed identifier.
- `SUPERSET_EMBED_ALLOWED_ORIGINS`: explicit local app origin(s) from the actual dev server; production `https://app.capix.cloud`.
- `SUPERSET_EMBED_SERVICE_USERNAME` / `SUPERSET_EMBED_SERVICE_PASSWORD`: dedicated issuer credentials, API/provisioner only.
- `SUPERSET_GUEST_TOKEN_JWT_SECRET`: strong signing secret, Superset only, never a Vite variable.

Set `EMBEDDED_SUPERSET` alongside existing feature flags, `GUEST_ROLE_NAME` to the dedicated guest role, and guest TTL to 300 seconds. Configure an explicit guest JWT audience matching Superset's canonical public origin and verify guest issuance uses it despite internal broker calls. Preserve current CSP directives while adding restrictive `frame-ancestors` entries for approved application origins; verify effective CSP and X-Frame-Options on the actual embedded route behind Dokploy/Cloudflare. Allowed-dashboard origins and response-header framing policy must both agree. Configure SDK referrer behavior compatibly with Superset 4.1.2's referrer check.

The API remains usable when embedding is disabled or unavailable. Metadata queries expose only a safe availability result, and the analytics page offers Spanish recovery states. Secrets are runtime values supplied through private local env files and Dokploy.

### 6. Manage lifecycle and session changes

Cache metadata using a session-aware query key. Request guest tokens afresh through the SDK callback and the shared API client, which already renews application authentication. Hide unnecessary embedded title/chart controls while preserving native filters. Fit the iframe using Tailwind descendant utilities on its container rather than custom CSS.

Track asynchronous mount completion so route changes, React StrictMode effect replay, and failed renewal clean up the SDK handle/iframe and abandon stale responses. Clear analytics query/mutation state when logout or identity change occurs. Use bounded loading/error states and retry by remounting cleanly. The SDK owns renewal scheduling; the app creates no background polling of Neon. Token renewal rechecks current signed claims; role revocation can remain effective only after the current guest token and Keycloak access token expire or renew, consistent with their bounded lifetimes.

## Risks / Trade-offs

- Guest denial accidentally removed for an unscoped principal → require a validated guest principal and applicable row rule; test missing, expired, forged, and empty-rule tokens.
- Keycloak mapper absent on live clients → verify issued access-token claims in each environment before enabling embedding; document client updates independently of realm templates.
- Superset 4.1.2 guest permissions differ from newer docs → validate the dedicated role/issuer against the pinned container and SDK rather than copying latest permissions.
- SDK can report mount completion before every chart query completes → verify chart results and native filter requests in browser tests; use actual page/iframe error evidence for readiness.
- Cross-origin browser policy blocks the iframe → inspect actual response headers and test local and production origins with referrer policy intact.
- Signed scope changes do not instantly revoke issued tokens → document five-minute guest lifetime and Keycloak token refresh behavior.

## Migration Plan

1. Implement and verify backend authorization/token broker, Superset guest enforcement/provisioning, and the React page with embedding disabled by default.
2. In development, update the live Keycloak web client mapper; configure private issuer/signing secrets; recreate Superset; provision the dedicated roles/account; enable embedding on Dashboard Principal with explicit local origins; record its embed UUID in local API configuration.
3. Test application-admin + analytics-admin, application-admin + scoped viewer/builder, application-admin without scope, and non-admin cases. Exercise both API denial and actual embedded chart/native-filter/export requests across scopes. Confirm direct Superset users retain access boundaries and tokens refresh beyond five minutes.
4. Run meaningful API/security tests, frontend lifecycle tests and `pnpm build`, and validate Compose with each environment's selected overlays. No Alembic migration or ERD change is required.
5. Push reviewed code and deploy with embedding disabled; configure production secrets and issuer role/account, update the live Keycloak web client, verify claims, and enable the published dashboard's embedding for the production app origin. Record production's embed UUID separately; no dashboard import is required for this integration.
6. Enable the production feature only after scoped account checks. Verify totals match direct Superset under identical filters, and existing application/Superset routes still work while users are active.
7. Rollback: disable embedding configuration, remove the dashboard's embed registration/allowed origins if retiring access, and restore prior configuration/code if needed. Revoke issuer credentials and rotate the dedicated guest secret if immediate guest-token invalidation is needed. Preserve dashboard metadata, chart registrations, and Neon business data.

## Open Questions

- Local and production embedded UUIDs must be obtained from each dashboard's embed settings during setup; the screenshot's numeric dashboard ID is insufficient.
- The precise local app origin must be recorded from the actual dev server used during verification.
