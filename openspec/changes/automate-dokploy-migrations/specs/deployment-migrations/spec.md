## Purpose

Coordinate production schema upgrades and application releases so new processes start only after the required migrations have succeeded, with observable failures and controlled handling of incompatible changes.

## ADDED Requirements

### Requirement: Deployment migration gate
Every production deployment SHALL run a migration check from the same release as the API and worker before starting their new processes. A failed check or migration SHALL block their startup and report deployment failure.

#### Scenario: Compatible pending revisions
- **WHEN** every pending revision is approved for automatic execution
- **THEN** the revisions are applied before new API and worker processes start
- **AND** the recorded database revision matches the release head

#### Scenario: Repeated deployment
- **WHEN** the same release is redeployed with no pending revisions
- **THEN** a fresh check succeeds without repeating applied migrations

#### Scenario: Migration failure
- **WHEN** migration execution fails
- **THEN** dependent new processes do not start and the failure remains visible in deployment logs

### Requirement: Migration eligibility
Automatic deployment SHALL reject pending revisions without an explicit review approving compatibility with the running application. Destructive changes and revisions requiring business-data preparation SHALL require their documented maintenance procedure.

#### Scenario: Manual preparation required
- **WHEN** the pending chain includes a column drop, a manual data split, or an unclassified revision
- **THEN** automatic execution stops before applying any pending revision and identifies the required procedure
- **AND** seeds and private JSON imports are not run automatically

### Requirement: Serialized and bounded execution
Migration runners SHALL serialize database changes, bound connection and lock waits, and reject unknown or ambiguous migration history without altering the revision marker.

#### Scenario: Concurrent deployment
- **WHEN** two runners target the same database
- **THEN** only one applies changes at a time and the other rechecks history after acquiring the lock or exits on timeout

#### Scenario: Unexpected history
- **WHEN** the database revision is unknown, ahead of the release, or ambiguous
- **THEN** the runner fails without downgrading or stamping the database

### Requirement: Deployment verification and privacy
Deployment verification SHALL exercise affected application data-fetching paths as well as process health. Logs SHALL identify revision transitions and failures without revealing credentials or business rows.

#### Scenario: Healthy process with broken query
- **WHEN** the API health endpoint succeeds but an affected authenticated data request fails
- **THEN** release verification fails and does not report the deployment as fully working
