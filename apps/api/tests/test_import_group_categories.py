import json

import pytest

from app.commands.import_group_categories import collect_pairs, load_rows, normalize_label


def test_load_rows_trims_labels_and_accepts_missing_group(tmp_path):
    source = tmp_path / "groups.json"
    source.write_text(
        json.dumps({"rows": [
            {"group": " Ejecución ", "categories": [" Fachada "]},
            {"group": None, "categories": ["Ventana"]},
        ]}),
        encoding="utf-8",
    )

    rows = load_rows(source)

    assert rows == [
        {"group": "Ejecución", "categories": ["Fachada"]},
        {"group": None, "categories": ["Ventana"]},
    ]


def test_collect_pairs_deduplicates_and_skips_rows_without_group():
    rows = [
        {"group": "Ejecución", "categories": ["Ventana", "Fachada"]},
        {"group": "Ejecución", "categories": ["Ventana"]},
        {"group": None, "categories": ["Otro"]},
    ]

    pairs, requested, missing_group_rows, duplicates = collect_pairs(rows)

    assert pairs == {("Ejecución", "Ventana"), ("Ejecución", "Fachada")}
    assert requested == 3
    assert missing_group_rows == 1
    assert duplicates == 1


def test_normalize_label_matches_spanish_accents_case_insensitively():
    assert normalize_label("Hojalatería") == normalize_label("hojalateria")
    assert normalize_label("  EJECUCIÓN  ") == normalize_label("Ejecucion")


@pytest.mark.parametrize("categories", [None, "Ventana", [" ", 1]])
def test_load_rows_rejects_invalid_categories(tmp_path, categories):
    source = tmp_path / "groups.json"
    source.write_text(json.dumps({"rows": [{"group": "Diseño", "categories": categories}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="categories"):
        load_rows(source)
