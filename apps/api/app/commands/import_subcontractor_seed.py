"""Import subcontractors and project assignments from JSON seeds (add-only, idempotent).

Specialities are managed by migrations and must already exist; seed keys match them
ignoring case, outer whitespace and accents. A seed subcontractor whose name already
belongs to another speciality is created as "<name> <speciality>" without accents
(for example "ICAM Hojalateria"), because each subcontractor has exactly one speciality and names
are unique.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal

_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")
_VOWEL_ACCENTS = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")


def normalized_name(value: str) -> str:
    """Python twin of the unique-index expression translate(lower(btrim(name)), ...)."""
    return value.strip(" ").lower().translate(_ACCENTS)


@dataclass(frozen=True)
class DatabaseState:
    project_names: dict[str, str]
    specialities: dict[int, str]
    subcontractors: list[tuple[int, str, int]]  # (id, name, speciality_id)
    links: set[tuple[str, int]]  # (project_id, subcontractor_id)


@dataclass(frozen=True)
class SubcontractorTarget:
    seed_name: str
    name: str
    speciality_id: int
    speciality: str
    existing_id: int | None
    renamed_from: str | None = None  # existing subcontractor of another speciality


@dataclass
class SeedPlan:
    targets: dict[str, SubcontractorTarget] = field(default_factory=dict)  # seed name -> target
    links: list[tuple[str, str]] = field(default_factory=list)  # (project_id, seed name)
    new_links: list[tuple[str, str]] = field(default_factory=list)
    skipped_projects: list[tuple[str, str]] = field(default_factory=list)  # rows without a subcontractor


def load_specialities(path: Path) -> dict[str, list[str]]:
    with path.open(encoding="utf-8") as source:
        payload: Any = json.load(source)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Speciality seed must be a non-empty object mapping specialities to subcontractor arrays")

    result: dict[str, list[str]] = {}
    seen_specialities: set[str] = set()
    seen_subcontractors: set[str] = set()
    for speciality, names in payload.items():
        if not isinstance(speciality, str) or not speciality.strip():
            raise ValueError("Every speciality key must be a non-empty string")
        if not isinstance(names, list):
            raise ValueError(f"Speciality {speciality!r} must map to an array")
        if normalized_name(speciality) in seen_specialities:
            raise ValueError(f"Duplicate speciality name in seed: {speciality.strip()!r}")
        seen_specialities.add(normalized_name(speciality))
        cleaned_names: list[str] = []
        for name in names:
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Speciality {speciality!r} contains an empty or invalid subcontractor name")
            cleaned = name.strip()
            if normalized_name(cleaned) in seen_subcontractors:
                raise ValueError(f"Duplicate subcontractor name in seed: {cleaned!r}")
            seen_subcontractors.add(normalized_name(cleaned))
            cleaned_names.append(cleaned)
        result[speciality.strip()] = cleaned_names
    return result


def load_project_rows(path: Path) -> list[dict[str, Any]]:
    """Read rows with either "subcontractors" (array) or "subcontractor" (string; empty means none)."""
    with path.open(encoding="utf-8") as source:
        payload: Any = json.load(source)
    if not isinstance(payload, list):
        raise ValueError("Project seed must be a JSON array")

    rows: list[dict[str, Any]] = []
    seen_projects: set[str] = set()
    for row_number, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Project seed row {row_number} must be an object")
        project_id = str(row.get("project_id", "")).strip()
        project_name = row.get("project_name")
        if not project_id or not isinstance(project_name, str) or not project_name.strip():
            raise ValueError(f"Project seed row {row_number} must have project_id and project_name")
        if "subcontractors" in row:
            subcontractors = row["subcontractors"]
            if not isinstance(subcontractors, list) or not all(isinstance(name, str) and name.strip() for name in subcontractors):
                raise ValueError(f"Project seed row {row_number} subcontractors must be an array of non-empty names")
        else:
            single = row.get("subcontractor")
            if not isinstance(single, str):
                raise ValueError(f"Project seed row {row_number} must have subcontractors or subcontractor")
            subcontractors = [single] if single.strip() else []
        if project_id in seen_projects:
            raise ValueError(f"Duplicate project_id in seed: {project_id}")
        seen_projects.add(project_id)
        names = [name.strip() for name in subcontractors]
        if len({normalized_name(name) for name in names}) != len(names):
            raise ValueError(f"Project seed row {row_number} contains duplicate subcontractor assignments")
        rows.append({"project_id": project_id, "project_name": project_name.strip(), "subcontractors": names})
    return rows


def load_state(db: Session) -> DatabaseState:
    return DatabaseState(
        project_names=dict(db.execute(text("SELECT id, name FROM app.project")).all()),
        specialities=dict(db.execute(text("SELECT id, name FROM app.speciality")).all()),
        subcontractors=[tuple(row) for row in db.execute(text("SELECT id, name, speciality_id FROM app.subcontractor")).all()],
        links={tuple(row) for row in db.execute(text("SELECT project_id, subcontractor_id FROM app.project_subcontractor")).all()},
    )


def plan_seed(state: DatabaseState, specialities: dict[str, list[str]], project_rows: list[dict[str, Any]]) -> SeedPlan:
    speciality_ids: dict[str, int] = {}
    for speciality_id, name in state.specialities.items():
        if normalized_name(name) in speciality_ids:
            raise ValueError(f"Database contains duplicate speciality name: {name!r}")
        speciality_ids[normalized_name(name)] = speciality_id
    existing: dict[str, tuple[int, str, int]] = {}
    for row in state.subcontractors:
        if normalized_name(row[1]) in existing:
            raise ValueError(f"Database contains duplicate subcontractor name: {row[1]!r}")
        existing[normalized_name(row[1])] = row

    plan = SeedPlan()
    target_names: dict[str, str] = {}
    for speciality, names in specialities.items():
        speciality_id = speciality_ids.get(normalized_name(speciality))
        if speciality_id is None:
            raise ValueError(f"Speciality {speciality!r} is not in app.speciality; apply the migrations that add it first")
        speciality_label = state.specialities[speciality_id]
        for name in names:
            target = _resolve_subcontractor(existing, name, speciality_id, speciality_label)
            clash = target_names.get(normalized_name(target.name))
            if clash is not None:
                raise ValueError(f"Seed subcontractors {clash!r} and {name!r} both resolve to {target.name!r}")
            target_names[normalized_name(target.name)] = name
            plan.targets[normalized_name(name)] = target

    for row in project_rows:
        project_name = state.project_names.get(row["project_id"])
        if project_name is None:
            raise ValueError(f"Project ID {row['project_id']!r} was not found in app.project")
        if project_name != row["project_name"]:
            raise ValueError(
                f"Project ID/name mismatch for {row['project_id']!r}: seed={row['project_name']!r}, database={project_name!r}"
            )
        if not row["subcontractors"]:
            plan.skipped_projects.append((row["project_id"], project_name))
        for name in row["subcontractors"]:
            target = plan.targets.get(normalized_name(name))
            if target is None:
                raise ValueError(f"Subcontractor {name!r} is not defined in the speciality seed")
            plan.links.append((row["project_id"], target.seed_name))
            if target.existing_id is None or (row["project_id"], target.existing_id) not in state.links:
                plan.new_links.append((row["project_id"], target.seed_name))
    return plan


def _resolve_subcontractor(existing, name: str, speciality_id: int, speciality: str) -> SubcontractorTarget:
    match = existing.get(normalized_name(name))
    if match is None or match[2] == speciality_id:
        return SubcontractorTarget(name, match[1] if match else name, speciality_id, speciality, match[0] if match else None)
    # The name belongs to another speciality: use "<name> <speciality>" without accents (reused on reruns).
    composed = f"{name} {speciality.translate(_VOWEL_ACCENTS)}"
    composed_match = existing.get(normalized_name(composed))
    if composed_match is not None and composed_match[2] != speciality_id:
        raise ValueError(f"Subcontractor {composed_match[1]!r} already exists under another speciality")
    return SubcontractorTarget(
        name,
        composed_match[1] if composed_match else composed,
        speciality_id,
        speciality,
        composed_match[0] if composed_match else None,
        renamed_from=match[1],
    )


def apply_plan(db: Session, plan: SeedPlan) -> None:
    ids: dict[str, int] = {}
    for key, target in plan.targets.items():
        if target.existing_id is not None:
            ids[target.seed_name] = target.existing_id
            continue
        ids[target.seed_name] = db.execute(
            text("INSERT INTO app.subcontractor (name, speciality_id) VALUES (:name, :speciality_id) RETURNING id"),
            {"name": target.name, "speciality_id": target.speciality_id},
        ).scalar_one()
    if plan.new_links:
        db.execute(
            text("""
                INSERT INTO app.project_subcontractor (project_id, subcontractor_id)
                VALUES (:project_id, :subcontractor_id)
                ON CONFLICT (project_id, subcontractor_id) DO NOTHING
            """),
            [{"project_id": project_id, "subcontractor_id": ids[name]} for project_id, name in plan.new_links],
        )


def format_plan(plan: SeedPlan, state: DatabaseState) -> str:
    targets = {target.seed_name: target for target in plan.targets.values()}
    created = [target for target in targets.values() if target.existing_id is None]
    lines = [f"Subcontractors: {len(created)} to create, {len(targets) - len(created)} already present."]
    for target in sorted(targets.values(), key=lambda target: (target.speciality, target.name.casefold())):
        status = "create" if target.existing_id is None else f"exists #{target.existing_id}"
        note = f"  (name {target.renamed_from!r} is already {_speciality_of(state, target.renamed_from)})" if target.renamed_from else ""
        lines.append(f"  [{status}] {target.name} — {target.speciality}{note}")
    lines.append(f"Project links: {len(plan.new_links)} to create, {len(plan.links) - len(plan.new_links)} already present.")
    for project_id, name in sorted(plan.links, key=lambda link: (link[0], link[1].casefold())):
        status = "create" if (project_id, name) in set(plan.new_links) else "exists"
        lines.append(f"  [{status}] {project_id} {state.project_names[project_id]} ← {targets[name].name}")
    if plan.skipped_projects:
        lines.append(f"Projects without a subcontractor in the seed (skipped): {len(plan.skipped_projects)}")
        lines.extend(f"  {project_id} {name}" for project_id, name in plan.skipped_projects)
    return "\n".join(lines)


def _speciality_of(state: DatabaseState, subcontractor_name: str | None) -> str:
    for _, name, speciality_id in state.subcontractors:
        if name == subcontractor_name:
            return state.specialities[speciality_id]
    return "another speciality"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("specialities_json", type=Path, help="Speciality-to-subcontractor mapping JSON")
    parser.add_argument("project_links_json", type=Path, help="Project-to-subcontractor mapping JSON")
    parser.add_argument("--apply", action="store_true", help="Commit the inserts; without this flag, run a dry run")
    args = parser.parse_args()

    specialities = load_specialities(args.specialities_json)
    project_rows = load_project_rows(args.project_links_json)
    with SessionLocal.begin() as db:
        if args.apply:
            # Block concurrent catalog edits between planning and inserting.
            db.execute(text("LOCK TABLE app.subcontractor, app.project_subcontractor IN SHARE ROW EXCLUSIVE MODE"))
        state = load_state(db)
        plan = plan_seed(state, specialities, project_rows)
        print(("APPLY" if args.apply else "DRY RUN (nothing written)") + "\n" + format_plan(plan, state))
        if args.apply:
            apply_plan(db, plan)
    if args.apply:
        print("Applied.")


if __name__ == "__main__":
    main()
