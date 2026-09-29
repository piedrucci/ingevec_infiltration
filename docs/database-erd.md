# Ingevec database ERD

This diagram reflects the current `app` schema represented by the SQLAlchemy models and Alembic migrations through revision `20260921_0015`. Analytics views are not shown as physical tables; the main view is described below the diagram.

```mermaid
erDiagram
    DIVISION_MANAGER ||--o{ PROJECT_MANAGER : manages
    PROJECT_MANAGER ||--o{ PROJECT_ADMIN : supervises
    PROJECT_ADMIN o|--o{ PROJECT : administers
    TYPOLOGY ||--o{ PROJECT : classifies
    LOCATION ||--o{ PROJECT : locates
    SUPERVISOR ||--o{ PROJECT : supervises
    PROJECT ||--o{ POSTVENTA_ITEM : contains
    CLASSIFICATION ||--o{ POSTVENTA_ITEM : classifies
    ITEM_TYPE ||--o{ POSTVENTA_ITEM : types
    SUBCONTRACTOR o|--o{ POSTVENTA_ITEM : performs
    EXCEL_IMPORT ||--o{ EXCEL_SOURCE_ROW : stages
    EXCEL_SOURCE_ROW o|--o| POSTVENTA_ITEM : normalizes_to
    FAILURE_CAUSE_CATEGORY ||--o{ FAILURE_CAUSE_CATEGORY_LINK : includes
    FAILURE_CAUSE ||--o{ FAILURE_CAUSE_CATEGORY_LINK : classified_as
    FAILURE_CAUSE ||--o{ FAILURE_CAUSE_ALIAS : has
    FAILURE_CAUSE o|--o{ POSTVENTA_ITEM : legacy_primary_cause
    POSTVENTA_ITEM ||--o{ POSTVENTA_ITEM_FAILURE_CAUSE : receives
    FAILURE_CAUSE ||--o{ POSTVENTA_ITEM_FAILURE_CAUSE : assigned
    DOCUMENT o|--o{ POSTVENTA_ITEM_FAILURE_CAUSE : source_document
    DOCUMENT ||--o{ DOCUMENT_POSTVENTA_ITEM : associates
    POSTVENTA_ITEM ||--o{ DOCUMENT_POSTVENTA_ITEM : associated_item
    DOCUMENT ||--o{ DOCUMENT_OUTBOX_EVENT : emits

    DIVISION_MANAGER {
        int id PK
        varchar name
    }
    PROJECT_MANAGER {
        int id PK
        int division_manager_id FK
        varchar name
    }
    PROJECT_ADMIN {
        int id PK
        int project_manager_id FK
        varchar name
    }
    TYPOLOGY {
        int id PK
        varchar name
    }
    LOCATION {
        int id PK
        varchar name
    }
    SUPERVISOR {
        int id PK
        varchar name
    }
    CLASSIFICATION {
        int id PK
        varchar name
    }
    ITEM_TYPE {
        int id PK
        varchar name
    }
    SUBCONTRACTOR {
        int id PK
        varchar name
    }
    EXCEL_IMPORT {
        uuid id PK
        varchar original_filename
        varchar file_hash UK
        varchar status
    }
    EXCEL_SOURCE_ROW {
        uuid id PK
        uuid excel_import_id FK
        varchar sheet_name
        int row_number
        jsonb raw_cells
        varchar normalization_status
    }
    PROJECT {
        varchar id PK
        uuid public_id UK
        varchar name
        int typology_id FK
        int location_id FK
        int supervisor_id FK
        int project_admin_id FK
    }
    FAILURE_CAUSE_CATEGORY {
        int id PK
        varchar code UK
        varchar display_name_es
        boolean is_active
    }
    FAILURE_CAUSE {
        int id PK
        varchar code UK
        varchar display_name_es
        boolean is_active
    }
    FAILURE_CAUSE_CATEGORY_LINK {
        int failure_cause_id PK, FK
        int category_id PK, FK
    }
    FAILURE_CAUSE_ALIAS {
        int id PK
        int failure_cause_id FK
        varchar normalized_alias UK
    }
    POSTVENTA_ITEM {
        int id PK
        uuid public_id UK
        uuid source_row_id FK, UK
        varchar project_id FK
        int classification_id FK
        int item_type_id FK
        int failure_cause_id FK
        int subcontractor_id FK
        text notes
        date request_date
    }
    POSTVENTA_ITEM_FAILURE_CAUSE {
        int postventa_item_id PK, FK
        int failure_cause_id PK, FK
        int source_document_id FK
        varchar assignment_source
        timestamptz assigned_at
    }
    DOCUMENT {
        int id PK
        uuid public_id UK
        varchar object_key UK
        varchar content_hash UK
        varchar original_filename
        varchar status
        numeric matching_confidence
        jsonb extracted_data
        text extracted_failure_cause
    }
    DOCUMENT_POSTVENTA_ITEM {
        int document_id PK, FK
        int postventa_item_id PK, FK
        varchar association_source
        numeric confidence
        timestamptz associated_at
    }
    DOCUMENT_OUTBOX_EVENT {
        int id PK
        int document_id FK
        varchar subject
        jsonb payload
        timestamptz published_at
    }
```

`analytics.postventa_item_dashboard` is a reporting view built from `postventa_item`, `project`, the catalog tables, failure-cause tables, document associations, and project-manager hierarchy. It is intentionally omitted from the physical-table ERD.
