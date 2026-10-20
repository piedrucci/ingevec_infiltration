"""Add the Hojalateria speciality and prevent duplicate speciality and subcontractor names."""

from alembic import op


revision = "20261020_0027"
down_revision = "20261020_0026"
branch_labels = None
depends_on = None

# Case-, whitespace- and accent-insensitive key, so "Impermeabilizacion" and
# "Impermeabilización" count as the same name. Keep in sync with the models and
# app.commands.import_subcontractor_seed.normalized_name.
NORMALIZED_NAME = "translate(lower(btrim(name)), 'áéíóúüñ', 'aeiouun')"
UNIQUE_INDEXES = {
    "speciality": "uq_speciality_name_normalized",
    "subcontractor": "uq_subcontractor_name_normalized",
}
SPECIALITY = "Hojalateria"


def upgrade() -> None:
    for table in UNIQUE_INDEXES:
        _reject_duplicate_names(table)
        # Rows were seeded directly in the database; make sure the identity sequence is past them.
        op.execute(f"""
            SELECT setval(pg_get_serial_sequence('app.{table}', 'id'), GREATEST(MAX(id), 1), MAX(id) IS NOT NULL)
            FROM app.{table}
        """)
    op.execute(f"""
        INSERT INTO app.speciality (name)
        SELECT '{SPECIALITY}'
        WHERE NOT EXISTS (
            SELECT 1 FROM app.speciality
            WHERE {NORMALIZED_NAME} = translate(lower('{SPECIALITY}'), 'áéíóúüñ', 'aeiouun')
        )
    """)
    for table, index in UNIQUE_INDEXES.items():
        op.execute(f"CREATE UNIQUE INDEX {index} ON app.{table} (({NORMALIZED_NAME}))")


def downgrade() -> None:
    for index in UNIQUE_INDEXES.values():
        op.execute(f"DROP INDEX app.{index}")
    # Subcontractors assigned to the speciality keep it (the foreign key would reject the delete).
    op.execute(f"""
        DELETE FROM app.speciality s
        WHERE s.name = '{SPECIALITY}'
          AND NOT EXISTS (SELECT 1 FROM app.subcontractor sc WHERE sc.speciality_id = s.id)
    """)


def _reject_duplicate_names(table: str) -> None:
    op.execute(f"""
        DO $$
        DECLARE duplicates text;
        BEGIN
            SELECT string_agg(names, '; ') INTO duplicates FROM (
                SELECT string_agg(id || ':' || name, ', ' ORDER BY id) AS names
                FROM app.{table}
                GROUP BY {NORMALIZED_NAME}
                HAVING count(*) > 1
            ) AS duplicated;
            IF duplicates IS NOT NULL THEN
                RAISE EXCEPTION 'Duplicate {table} names must be merged or renamed before this migration: %', duplicates;
            END IF;
        END
        $$;
    """)
