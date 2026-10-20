import json

import pytest

from app.commands.import_subcontractor_seed import (
    DatabaseState,
    format_plan,
    load_project_rows,
    load_specialities,
    normalized_name,
    plan_seed,
)


def state(subcontractors=(), links=()):
    return DatabaseState(
        project_names={"751": "City Box", "766": "Procentro El Salto", "728": "Mirador San Carlos"},
        specialities={3: "Fachada", 5: "Hojalateria"},
        subcontractors=list(subcontractors),
        links=set(links),
    )


def rows(*links):
    names = {"751": "City Box", "766": "Procentro El Salto", "728": "Mirador San Carlos"}
    return [{"project_id": project_id, "project_name": names[project_id], "subcontractors": subs} for project_id, subs in links]


def test_normalized_name_matches_the_unique_index_expression():
    assert normalized_name("  Hojalatería ") == normalized_name("HOJALATERIA") == "hojalateria"


def test_new_subcontractor_matches_speciality_ignoring_accents():
    plan = plan_seed(state(), {"Hojalateria": ["PDA"]}, rows(("751", ["PDA"])))
    target = plan.targets["pda"]
    assert (target.name, target.speciality_id, target.existing_id, target.renamed_from) == ("PDA", 5, None, None)
    assert plan.new_links == [("751", "PDA")]


def test_name_used_by_another_speciality_gets_the_speciality_suffix():
    plan = plan_seed(state(subcontractors=[(65, "ICAM", 3)], links=[("766", 65)]), {"Hojalateria": ["ICAM"]}, rows(("751", ["ICAM"]), ("766", ["ICAM"])))
    target = plan.targets["icam"]
    assert (target.name, target.existing_id, target.renamed_from) == ("ICAM Hojalateria", None, "ICAM")
    # The Fachada link on 766 does not count: the Hojalateria subcontractor is new.
    assert plan.new_links == [("751", "ICAM"), ("766", "ICAM")]


def test_suffix_drops_accents_from_the_speciality():
    current = DatabaseState(project_names={}, specialities={2: "Impermeabilización", 3: "Fachada"}, subcontractors=[(65, "ICAM", 3)], links=set())
    assert plan_seed(current, {"Impermeabilizacion": ["ICAM"]}, []).targets["icam"].name == "ICAM Impermeabilizacion"


def test_rerun_reuses_created_rows_and_links():
    current = state(subcontractors=[(65, "ICAM", 3), (91, "ICAM Hojalateria", 5), (88, "PDA", 5)], links=[("751", 91), ("751", 88)])
    plan = plan_seed(current, {"Hojalateria": ["ICAM", "PDA"]}, rows(("751", ["ICAM", "PDA"])))
    assert [target.existing_id for target in plan.targets.values()] == [91, 88]
    assert plan.new_links == []


def test_composed_name_under_another_speciality_blocks():
    current = state(subcontractors=[(65, "ICAM", 3), (70, "ICAM Hojalateria", 3)])
    with pytest.raises(ValueError, match="already exists under another speciality"):
        plan_seed(current, {"Hojalateria": ["ICAM"]}, [])


def test_missing_speciality_and_project_mismatch_block():
    with pytest.raises(ValueError, match="apply the migrations"):
        plan_seed(state(), {"Pintura": ["X"]}, [])
    with pytest.raises(ValueError, match="mismatch"):
        plan_seed(state(), {"Hojalateria": ["PDA"]}, [{"project_id": "751", "project_name": "Other", "subcontractors": ["PDA"]}])
    with pytest.raises(ValueError, match="not defined in the speciality seed"):
        plan_seed(state(), {"Hojalateria": ["PDA"]}, rows(("751", ["Unknown"])))


def test_empty_subcontractor_rows_are_reported_as_skipped():
    plan = plan_seed(state(), {"Hojalateria": ["PDA"]}, rows(("728", [])))
    assert plan.skipped_projects == [("728", "Mirador San Carlos")]
    assert "Projects without a subcontractor" in format_plan(plan, state())


def test_loaders_accept_single_subcontractor_rows_and_reject_duplicates(tmp_path):
    projects = tmp_path / "projects.json"
    projects.write_text(json.dumps([
        {"project_id": 751, "project_name": "City Box", "subcontractor": "ICAM"},
        {"project_id": 728, "project_name": "Mirador San Carlos", "subcontractor": ""},
    ]), encoding="utf-8")
    assert load_project_rows(projects) == [
        {"project_id": "751", "project_name": "City Box", "subcontractors": ["ICAM"]},
        {"project_id": "728", "project_name": "Mirador San Carlos", "subcontractors": []},
    ]
    seed = tmp_path / "specialities.json"
    seed.write_text(json.dumps({"Hojalateria": ["ICAM", " icam "]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate subcontractor"):
        load_specialities(seed)
