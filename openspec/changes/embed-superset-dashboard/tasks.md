# Tasks

## 1. Authorization and environment configuration

- [x] 1.1 Add optional embedding settings to API/Superset configuration and both environment examples, with embedding disabled by default; verify disabled/missing settings preserve existing API startup and return a safe availability error.
- [x] 1.2 Wire settings to API, Superset, and provisioner Compose services without putting secrets in browser settings; validate development and production overlays and inspect redacted effective settings.
- [ ] 1.3 Add full-path scope-group mappers to both Keycloak web-client realm templates and document live-client updates/session renewal; verify fresh development web access tokens have API audience, analytics roles, and groups.
- [x] 1.4 Add analytics authorization and scope construction using `current_claims`/`require_admin`; test signed-claim role requirements, application-admin-only denial, scoped role union, explicit analytics-admin access, malformed claims/IDs, injection attempts, and excessive scope denial.

## 2. Superset guest security and provisioning

- [x] 2.1 Enable conditional embedding, a strong runtime guest secret, explicit audience, dedicated guest role, five-minute expiry, and restrictive frame ancestors while preserving other CSP directives; verify emitted embedded-route headers and audience against Superset 4.1.2.
- [x] 2.2 Adapt the custom security manager for validated guests with required global row rules and install it whenever embedding is enabled; test missing/empty rules, non-guest requests, uncurated dataset denial, direct Keycloak scope regression, and scope-specific cache keys.
- [ ] 2.3 Add idempotent provisioning for the dedicated guest role and database-authenticated token issuer account; verify the minimum 4.1.2 permissions render charts/native filters and permit issuance, while SQL Lab/write/other-dashboard access and ordinary Public dataset access remain denied.
- [x] 2.4 Document Superset guest-role setup and per-dashboard explicit origin/embed-UUID configuration in `docs/superset-analytics.md`; verify the steps against the local 4.1.2 container and preserve existing dashboard/chart/dataset metadata.

## 3. API token broker

- [x] 3.1 Implement the embedding service with internal Superset login/guest issuance, bounded timeouts, in-memory issuer session reuse, one authentication retry, and sanitized failures; test issuer expiration, connection errors, and absence of credentials/tokens in logs.
- [x] 3.2 Add authorized `GET /v1/analytics/dashboard` and `POST /v1/analytics/guest-token` with typed schemas, fixed configured dashboard, no client-controlled scope, and no-store token responses; test successful scope payloads, 401/403/503 cases, and arbitrary request-parameter rejection.
- [ ] 3.3 Document endpoint contracts, issuer credentials, expiration and revocation behavior; verify API tests pass with synthetic claims and mocked upstream calls, and verify an actual local token request reaches Superset with the expected dashboard resource and row rule.

## 4. React integration

- [x] 4.1 Install a pinned compatible Embedded SDK with pnpm and record compatibility/refresh/unmount behavior; verify the package API against local Superset 4.1.2 and the committed pnpm lockfile.
- [x] 4.2 Extend shared `api.ts` with typed metadata and token calls and shared auth helpers with analytics entitlement/session identity; verify all requests use existing authenticated access-token renewal and components never read raw Keycloak tokens.
- [x] 4.3 Add feature-local metadata queries, token mutation and embedding lifecycle hook; test fresh token callbacks, refresh failure, stale async mounts, StrictMode replay, cleanup, and identity/logout cache isolation.
- [ ] 4.4 Build `/analytics` with `Analítica` navigation, shadcn loading/error/retry states, responsive Tailwind iframe sizing, and Spanish copy; verify current admin gating, authorization-denied/unavailable states, keyboard use, and preservation of `/`.
- [ ] 4.5 Document local UI setup and recovery behavior; run frontend lifecycle tests and `pnpm build`, then observe one iframe mount and clean unmount while navigating between application routes.

## 5. Local integration and rollout preparation

- [ ] 5.1 Configure private development secrets, provision dedicated accounts/roles, set the actual dev origin and local embed UUID, and enable embedding; verify displayed chart counts match direct Superset under the same filters.
- [ ] 5.2 Exercise two disjoint project scopes, division/project union, analytics-admin access, missing scope, malformed/expired/forged tokens, unrelated dashboard requests, native filters and permitted exports; verify actual requests and cached responses never reveal another scope's rows.
- [ ] 5.3 Keep the embedded page open beyond five minutes, then navigate/logout and expire or change application authorization; verify renewal works for authorized sessions and failures stop the embedded session without affecting other routes.
- [x] 5.4 Document production enablement and rollback in `docs/deployment.md` and update contributor guidance for the completed feature; verify the runbook distinguishes live Keycloak updates, Superset provisioning, embed metadata, runtime secrets, and application code deployment, with no application migration required.
- [x] 5.5 Run the API suite, frontend build/tests, and relevant Compose validation after integration; record results and any environment-dependent production checks still required before enabling production.

## Workflow follow-up

- Push reviewed implementation and deploy with embedding disabled. Configure production issuer/signing secrets, update live Keycloak claims, provision dedicated roles, and register the existing published dashboard for the explicit production app origin.
- Set the production embed UUID and enable only after authorized scoped-viewer checks; observe native Superset and existing application behavior while the site is in use.
- Archive this change after implementation and validation are complete; preserve operational secrets and exported analytics bundles outside Git.
