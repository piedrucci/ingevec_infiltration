# Proposal

## Why

The published Superset dashboard is available separately from the React administrative UI. Embedding it lets authorized staff consult the same charts and filters inside the application while preserving the existing project/division access boundaries.

## What Changes

- Add `/analytics` with Spanish navigation label `Analítica`, embedding the configured Dashboard Principal through the official Superset Embedded SDK.
- Add authenticated dashboard metadata and guest-token API endpoints. Scope and dashboard identity come from verified claims and server configuration.
- Include analytics scope groups in the Keycloak web client's access tokens, and enforce Superset role entitlement separately from the application `admin` role.
- Enable Superset embedding with an explicit origin allowlist, a dedicated guest role, and a restricted server-side token issuer account.
- Adapt Superset's custom security manager to preserve signed guest-token row filters without applying the Keycloak user's missing-role denial to valid guests. Missing guest scopes continue to deny access.
- Document local setup, verification, production rollout, and rollback; preserve the current administrative UI access gate.

## Capabilities

### New Capabilities

- `embedded-analytics`: Authenticated dashboard embedding, guest-token issuance and renewal, verified user scope, Superset guest access isolation, and deployment configuration.

### Modified Capabilities

None. Existing frontend and backend implementation rules apply unchanged.

## Impact

Affected areas: `apps/web/src/features/analytics/`, shared API/auth infrastructure and routing, `apps/api/app/auth.py`, API routes/services/settings, Superset security configuration and provisioning, Keycloak realm templates, Compose environment wiring, both environment examples, and analytics/deployment documentation. Add a pinned, Superset 4.1.2-compatible `@superset-ui/embedded-sdk` dependency using pnpm.

No application database schema change is planned. This proposal covers one configured dashboard and the current admin-only React application; opening the application to analytics-only viewers is a separate access-policy change. Charts, dashboard content, and Neon business data are not recreated during this work.
