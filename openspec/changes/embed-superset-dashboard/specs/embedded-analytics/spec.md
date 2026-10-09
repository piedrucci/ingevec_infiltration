# Embedded Analytics Specification Delta

## Purpose

Provide the published analytics dashboard inside the authenticated administrative application while enforcing each user's verified analytics entitlement and project/division scope.

## ADDED Requirements

### Requirement: Analytics page
The application SHALL expose the configured dashboard at `/analytics` through Spanish navigation labelled `Analítica`, within the existing administrative access policy. Existing home dashboard behavior SHALL remain available.

#### Scenario: Authorized administrator opens analytics
- **WHEN** an application administrator with analytics entitlement opens `/analytics`
- **THEN** the configured dashboard and its native filters are available within the application
- **AND** charts are read-only for the embedded user

#### Scenario: Application role missing
- **WHEN** a user without the application administrator role attempts to access analytics
- **THEN** the administrative UI and embedding API deny access

### Requirement: Verified analytics entitlement
Embedding access SHALL require validated application authentication and an analytics role. Only `superset_admin` SHALL grant unrestricted analytics scope. `superset_viewer` and `superset_dashboard_builder` SHALL require a valid project or division scope in signed claims. Missing or malformed scope SHALL fail closed.

#### Scenario: Scoped viewer
- **WHEN** an application administrator with `superset_viewer` has verified project scope
- **THEN** embedding access is limited to that project

#### Scenario: Application administrator without analytics scope
- **WHEN** a user has only the application administrator role, or a scoped analytics role without valid scope
- **THEN** token issuance is denied with no token returned

#### Scenario: Analytics administrator
- **WHEN** an application administrator also has verified `superset_admin`
- **THEN** the configured dashboard can display all authorized analytics rows

### Requirement: Server-owned dashboard and scope
The embedding API SHALL select the dashboard from environment configuration and construct row restrictions exclusively from verified authorization claims. Caller-supplied dashboard identifiers, SQL, role names, or scope selections SHALL NOT determine token access.

#### Scenario: Client attempts broader access
- **WHEN** a client submits arbitrary dashboard or scope parameters
- **THEN** the API rejects them and issues no broader access

### Requirement: Guest access isolation
Embedded tokens SHALL authorize only the configured dashboard and enforce row restrictions on all three curated analytics datasets, including native filters and exports when available. Native Superset authentication SHALL preserve existing Keycloak role scope. Ordinary anonymous/Public access SHALL receive no dataset grants from embedding setup.

#### Scenario: Guest selects an unauthorized project
- **WHEN** an embedded user changes filter parameters or attempts a chart request outside their scope
- **THEN** rows outside the signed token scope are not returned

#### Scenario: Guest has no applicable row rule
- **WHEN** a guest token has no applicable nonempty scope rule
- **THEN** the curated datasets return no rows or deny access

#### Scenario: Existing authenticated Superset viewer
- **WHEN** a scoped Keycloak viewer opens Superset directly
- **THEN** their current project/division restrictions continue to apply

### Requirement: Token lifecycle and privacy
Tokens SHALL expire within five minutes and be renewed only after reauthorizing the application's current user. Token responses SHALL prevent HTTP caching. Browser token state SHALL remain in memory and be discarded on logout or user change; tokens and issuer credentials SHALL NOT appear in URLs, logs, persistent storage, or committed assets.

#### Scenario: Token expires while dashboard is open
- **WHEN** the dashboard requires a refreshed token
- **THEN** the API revalidates the current user and renews authorized access without requiring Superset login

#### Scenario: Authorization expires or changes
- **WHEN** a renewal request has invalid authentication or no longer has analytics entitlement
- **THEN** renewal fails and the application stops presenting the embedded session with a Spanish recovery message

### Requirement: Explicit embedding origins
Each environment SHALL configure an explicit allowed application origin for dashboard embedding and compatible browser framing policy. An unauthorized origin SHALL be denied. Secrets SHALL stay server-side and local and production dashboards SHALL have independently configured embedding identifiers.

#### Scenario: Production embedding
- **WHEN** the configured dashboard is embedded from `https://app.capix.cloud`
- **THEN** the browser can render the authorized dashboard

#### Scenario: Unapproved embedding host
- **WHEN** another origin tries to embed the dashboard
- **THEN** Superset and browser framing policy deny the request

### Requirement: Recoverable analytics failures
The application SHALL display Spanish loading, access-denied, unavailable, and recoverable error states. Disabled or incomplete embedding configuration and Superset outages SHALL fail without disrupting other application routes or leaking upstream credentials. Navigation SHALL clean up embedding resources.

#### Scenario: Superset unavailable
- **WHEN** the token service cannot reach Superset within its bounded timeout
- **THEN** the API returns a sanitized availability error and the page provides a retry action

#### Scenario: User navigates away
- **WHEN** the analytics page unmounts
- **THEN** its iframe and token-renewal work are cleaned up
