import copy
import json

import pytest

from app.commands.apply_cause_assignments import Snapshot, load_rows, plan_assignments

GROUPS = {1: {"code": "EJECUCION", "name": "Ejecución"}, 2: {"code": "PROPIETARIO", "name": "Propietario"}, 3: {"code": "DISENO", "name": "Diseño"}}
CATEGORIES = {10: {"code": "WINDOWS", "name": "Ventana", "active": True}, 11: {"code": "SHEET_METAL", "name": "Hojalateria", "active": True}}
PROVENANCE = {"assignment_source": "MANUAL", "assigned_at": "2026-10-01T00:00:00+00:00", "assigned_by": "tester", "source_document_id": 7}


def cause(code, name, category_id, group_id=None, active=True):
    return {"code": code, "name": name, "description": None, "active": active, "category_id": category_id, "group_id": group_id}


def snapshot(**overrides):
    base = Snapshot(
        items={1: {"project_id": "712", "notes": "Depto A", "primary": 100}, 2: {"project_id": "712", "notes": "Depto B", "primary": 100},
               3: {"project_id": "800", "notes": "Depto C", "primary": None}},
        groups=GROUPS,
        categories=CATEGORIES,
        junction={(10, 1), (10, 2), (10, 3), (11, 1), (11, 2)},
        causes={100: cause("BROKEN_SEALS__WINDOWS", "Sellos cortados", 10), 101: cause("PVC", "PVC inferior", 10),
                102: cause("CUBIERTA", "Mala ejecución cubierta", 11)},
        aliases={"ventana sellos cortados": 100},
        links={1: {100: dict(PROVENANCE)}, 2: {100: dict(PROVENANCE), 101: dict(PROVENANCE)}},
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def row(notes, project, *associations):
    return {"project_id": project, "notes": notes,
            "associated_causes": [{"group": g, "category": c, "cause": n} for g, c, n in associations]}


def test_single_group_cause_gets_group_and_item_links_are_kept():
    plan = plan_assignments(snapshot(), [
        row("Depto A", "712", ("Ejecución", "Ventana", "Sellos cortados")),
        row("Depto B", "712", ("Ejecución", "Ventana", "Sellos cortados"), ("Ejecución", "Ventana", "PVC inferior")),
    ])
    assert plan.blockers == []
    assert {(u["code"], u["group_id"]) for u in plan.group_updates} == {("BROKEN_SEALS__WINDOWS", 1), ("PVC", 1)}
    assert plan.item_changes == [] and plan.creations == [] and plan.retirements == []


def test_cause_used_by_several_groups_is_split_and_links_keep_provenance():
    plan = plan_assignments(snapshot(), [
        row("Depto A", "712", ("Ejecución", "Ventana", "Sellos cortados")),
        row("Depto B", "712", ("Propietario", "Ventana", "sellos  CORTADOS"), ("Propietario", "Ventana", "PVC inferior")),
    ])
    assert plan.blockers == []
    assert plan.retirements == [{"cause_id": 100, "code": "BROKEN_SEALS__WINDOWS", "category_id": 10}]
    assert {(c["code"], c["group_id"], c["alias"], c["split_from"]) for c in plan.creations} == {
        ("BROKEN_SEALS__WINDOWS__EJECUCION", 1, "ejecucion ventana sellos cortados", 100),
        ("BROKEN_SEALS__WINDOWS__PROPIETARIO", 2, "propietario ventana sellos cortados", 100),
    }
    changes = {c["item_id"]: c for c in plan.item_changes}
    assert changes[1] == {"item_id": 1, "remove": [100], "after": [
        {"code": "BROKEN_SEALS__WINDOWS__EJECUCION", "action": "repoint", "from_cause_id": 100}]}
    assert changes[2]["remove"] == [100]
    assert {a["action"] for a in changes[2]["after"]} == {"keep", "repoint"}
    assert plan.summary["links_removed"] == 0 and plan.summary["links_repointed"] == 2


def test_missing_cause_is_created_and_items_without_causes_get_links():
    plan = plan_assignments(snapshot(), [row("Depto C", "800", ("Ejecución", "Hojalatería", "Gárgola rota"))])
    assert plan.blockers == []
    assert plan.creations == [{"code": "GARGOLA_ROTA", "name": "Gárgola rota", "description": None, "category_id": 11,
                               "group_id": 1, "alias": "hojalateria gargola rota", "split_from": None}]
    assert plan.item_changes == [{"item_id": 3, "remove": [], "after": [{"code": "GARGOLA_ROTA", "action": "add", "from_cause_id": None}]}]
    assert "category 'Hojalatería' -> 'Hojalateria'" in plan.normalized_matches


def test_stale_legacy_primary_pointer_is_resynchronized():
    snap = snapshot()
    snap.items[2]["primary"] = 101
    plan = plan_assignments(snap, [row("Depto B", "712", ("Ejecución", "Ventana", "Sellos cortados"), ("Ejecución", "Ventana", "PVC inferior"))])
    assert [c["item_id"] for c in plan.item_changes] == [2]
    assert {a["action"] for a in plan.item_changes[0]["after"]} == {"keep"} and plan.item_changes[0]["remove"] == []


def test_json_is_the_truth_for_matched_items():
    plan = plan_assignments(snapshot(), [row("Depto B", "712", ("Ejecución", "Ventana", "PVC inferior"))])
    assert plan.item_changes == [{"item_id": 2, "remove": [100], "after": [{"code": "PVC", "action": "keep", "from_cause_id": 101}]}]
    assert plan.summary["database_items_not_in_json"] == 2


@pytest.mark.parametrize("rows, message", [
    ([row("Depto A", "999", ("Ejecución", "Ventana", "PVC inferior"))], "project mismatch"),
    ([row("Depto C", "800", ("Diseño", "Hojalateria", "PVC inferior"))], "does not contain category"),
    ([row("Depto C", "800", ("Otro", "Ventana", "PVC inferior"))], "group not found"),
    ([row("Depto A", "712", ("Ejecución", "Ventana", "PVC inferior")), row("Depto B", "712", (None, "Ventana", "PVC inferior"))], "with and without a group"),
    # Item 2 is absent from the JSON but uses the cause that must be split.
    ([row("Depto A", "712", ("Ejecución", "Ventana", "Sellos cortados")), row("Depto C", "800", ("Propietario", "Ventana", "Sellos cortados"))],
     "not in the JSON but uses a cause that would be split"),
])
def test_blockers(rows, message):
    assert any(message in blocker for blocker in plan_assignments(snapshot(), rows).blockers)


def test_unmatched_notes_are_reported_and_skipped():
    plan = plan_assignments(snapshot(), [row("No existe", "1", ("Ejecución", "Ventana", "PVC inferior"))])
    assert plan.blockers == [] and plan.item_changes == []
    assert plan.summary["unmatched_rows"] == 1


def test_duplicate_database_notes_block():
    snap = snapshot()
    snap.items[3]["notes"] = "Depto A"
    plan = plan_assignments(snap, [row("Depto A", "712", ("Ejecución", "Ventana", "PVC inferior"))])
    assert any("matches 2 items" in blocker for blocker in plan.blockers)


def test_rerun_after_split_plans_no_changes():
    rows = [row("Depto A", "712", ("Ejecución", "Ventana", "Sellos cortados")),
            row("Depto B", "712", ("Propietario", "Ventana", "Sellos cortados"), ("Propietario", "Ventana", "PVC inferior"))]
    after = snapshot()
    after.causes = copy.deepcopy(after.causes)
    after.causes[100].update(active=False, category_id=None)
    after.causes[101]["group_id"] = 2
    after.causes[200] = cause("BROKEN_SEALS__WINDOWS__EJECUCION", "Sellos cortados", 10, 1)
    after.causes[201] = cause("BROKEN_SEALS__WINDOWS__PROPIETARIO", "Sellos cortados", 10, 2)
    after.aliases = {"ventana sellos cortados": 100, "ejecucion ventana sellos cortados": 200, "propietario ventana sellos cortados": 201}
    after.links = {1: {200: dict(PROVENANCE)}, 2: {201: dict(PROVENANCE), 101: dict(PROVENANCE)}}
    after.items = copy.deepcopy(after.items)
    after.items[1]["primary"], after.items[2]["primary"] = 200, 101
    plan = plan_assignments(after, rows)
    assert plan.blockers == []
    assert (plan.group_updates, plan.creations, plan.retirements, plan.item_changes) == ([], [], [], [])


def test_fingerprint_changes_with_links():
    snap = snapshot()
    changed = snapshot(links={1: {101: dict(PROVENANCE)}})
    assert snap.fingerprint() != changed.fingerprint()


def test_load_rows_validates_structure(tmp_path):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({"rows": [row(" Depto A ", "712", (None, "Ventana", "PVC"))]}), encoding="utf-8")
    assert load_rows(path)[0]["notes"] == "Depto A"
    path.write_text(json.dumps({"rows": [row("A", "1"), row("A", "1")]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate notes"):
        load_rows(path)
    path.write_text(json.dumps({"rows": [{"notes": "A", "project_id": "1", "associated_causes": [{"group": "X", "category": "", "cause": "Y"}]}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid association"):
        load_rows(path)
