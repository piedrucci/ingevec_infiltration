# Web Components Specification

## Purpose

Rules that humans and AI agents SHALL follow when creating or modifying UI in `apps/web` (Ingevec Postventa administrative UI). Stack: React 19, TypeScript, Vite, React Router, `keycloak-js`, TanStack Query, TanStack Table, shadcn/ui, Tailwind.

This is a Vite SPA, not Next.js: agents SHALL NOT use `"use client"`, the App Router, server components, or `next/*` imports.

## Requirements

### Requirement: File placement
New code SHALL follow `apps/web/src` and keep feature-specific code separate from shared infrastructure. `components/ui/` contains shadcn primitives; `components/` contains shared components; `features/<feature>/` contains feature UI, types, and local queries. Top-level `queries/` is for query modules shared across features. Keep shared API, auth, query-client, types, and utility modules in their existing locations; extend them instead of duplicating them.

#### Scenario: New feature screen
- **WHEN** an agent adds a screen for a new domain object
- **THEN** it creates `features/<feature>/` for UI and feature-specific data hooks
- **AND** it places a query module in top-level `queries/` only when that query/key factory is shared across features
- **AND** it does not put feature logic in `components/ui/`

### Requirement: Collection views use TanStack Table and TanStack Query
Collection screens that show tabular data SHALL use `@tanstack/react-table` for table state and rendering. Server state SHALL be fetched and cached with `@tanstack/react-query`. Small non-tabular lists used for navigation, options, or short summaries MAY use semantic lists instead of TanStack Table.

#### Scenario: Building a list
- **WHEN** an agent creates a list component
- **THEN** columns are defined as typed `ColumnDef<T>[]`, preferably in a feature-local `columns.tsx` when the table is substantial or reused
- **AND** rows use the shared `DataTable` when its API fits, or shadcn/ui `Table` primitives for custom composition
- **AND** data comes from a hook in the feature's query module or a shared query module, never from `useEffect` + `fetch`
- **AND** loading, error, and empty states are all rendered

#### Scenario: Large datasets
- **WHEN** the API endpoint supports pagination, sorting, or filtering
- **THEN** the table uses server-side state (`manualPagination`, `manualSorting`, `manualFiltering`) and passes that state into the query key

### Requirement: Data fetching and mutations
Data reads that represent server state SHALL use TanStack Query and the shared `api.ts` client. Server mutations SHALL use TanStack Query mutation APIs and the shared client. One-off imperative operations such as downloading a document MAY call an `api.ts` function directly when caching the result is not useful.

#### Scenario: Query keys
- **WHEN** an agent adds a query
- **THEN** its key comes from a key factory in `queries/` (e.g. `postventaKeys.list(filters)`)

#### Scenario: Mutations
- **WHEN** a mutation changes imports, documents, items, causes, or associations
- **THEN** it invalidates every affected query key
- **AND** it does not assume the backend dashboard cache (5 minutes) is fresh

#### Scenario: Authentication
- **WHEN** a request is made
- **THEN** it uses the authenticated client in `api.ts`
- **AND** components never read or store Keycloak tokens directly

### Requirement: UI uses shadcn/ui and Tailwind
Components SHALL use shadcn/ui primitives where available and Tailwind utility classes for component styling. `styles.css` SHALL be reserved primarily for design tokens, reset/base styles, and genuinely global rules; new component-specific global selectors SHOULD be avoided, and existing legacy selectors SHOULD be removed as the affected components are migrated. Inline styles and CSS modules SHOULD NOT be introduced.

#### Scenario: Adding a primitive
- **WHEN** a needed primitive is missing from `components/ui/`
- **THEN** it is added with `pnpm dlx shadcn@latest add <component>`
- **AND** it is not hand-written or taken from another component library

#### Scenario: Styling
- **WHEN** an agent styles a component
- **THEN** it uses Tailwind classes, merging conditional class names with `cn()` where useful
- **AND** component-specific rules are not added to global `styles.css` unless a real limitation of utilities or a reusable global behavior requires them
- **AND** it does not add inline styles or CSS modules

### Requirement: Types
Props, API responses, and table rows SHALL be typed.

#### Scenario: API shapes
- **WHEN** a component consumes API data
- **THEN** its types live in `types.ts` (or a feature-local `types.ts`) and match the API schema
- **AND** `any` is avoided; if an external library forces it in a shared abstraction, the use is isolated to that abstraction

### Requirement: Routing and authorization
Routes SHALL use React Router and respect authentication. Administrative screens SHALL require the authenticated administrator role.

#### Scenario: Admin actions
- **WHEN** a component exposes an admin-only action (uploads, imports, association edits)
- **THEN** the UI hides or disables it for non-admins
- **AND** the spec treats this as a convenience only, because the API enforces `require_admin`

### Requirement: Spanish user-facing text
User-facing labels, messages, and column headers SHALL be in Spanish with correct accents (e.g. `Diseño`, `Ejecución`). Code identifiers remain in English.

#### Scenario: User-facing copy
- **WHEN** an agent adds or changes UI text
- **THEN** user-facing copy is written in Spanish with correct accents

### Requirement: Business data stays private
Components SHALL NOT embed business data or expose storage directly.

#### Scenario: Documents
- **WHEN** a component links to a PDF or workbook
- **THEN** it uses an API endpoint
- **AND** it never uses a direct SeaweedFS URL or committed credentials

#### Scenario: Fixtures
- **WHEN** tests or stories need sample data
- **THEN** they use synthetic data, never rows from `data/` or database dumps

### Requirement: Package management
The frontend SHALL use pnpm.

#### Scenario: Adding or running tooling
- **WHEN** an agent installs a dependency or runs a script
- **THEN** it uses `pnpm add`, `pnpm <script>`, or `pnpm dlx`
- **AND** it never runs `npm` or `yarn`, or creates `package-lock.json` or `yarn.lock`

### Requirement: Verification
Frontend changes SHALL pass the web production build.

#### Scenario: Before finishing
- **WHEN** an agent finishes a frontend change
- **THEN** `pnpm build` succeeds from `apps/web`
