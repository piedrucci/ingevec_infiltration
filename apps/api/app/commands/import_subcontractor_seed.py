"""Import speciality/subcontractor catalogs and project assignments from JSON seeds."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal


@dataclass(frozen=True)
class ImportSummary:
    specialities: int
    subcontractors: int
    project_links: int
    specialities_inserted: int
    subcontractors_inserted: int
    project_links_inserted: int


def load_specialities(path: Path) -> dict[str, list[str]]:
    with path.open(encoding="utf-8") as source:
        payload: Any = json.load(source)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Speciality seed must be a non-empty object mapping specialities to subcontractor arrays")

    result: dict[str, list[str]] = {}
    seen_subcontractors: set[str] = set()
    for speciality, names in payload.items():
        if not isinstance(speciality, str) or not speciality.strip():
            raise ValueError("Every speciality key must be a non-empty string")
        if not isinstance(names, list):
            raise ValueError(f"Speciality {speciality!r} must map to an array")
        cleaned_names: list[str] = []
        for name in names:
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Speciality {speciality!r} contains an empty or invalid subcontractor name")
            cleaned = name.strip()
            key = cleaned.casefold()
            if key in seen_subcontractors:
                raise ValueError(f"Duplicate subcontractor name in seed: {cleaned!r}")
            seen_subcontractors.add(key)
            cleaned_names.append(cleaned)
        cleaned_speciality = speciality.strip()
        if cleaned_speciality in result:
            raise ValueError(f"Duplicate speciality name in seed: {cleaned_speciality!r}")
        result[cleaned_speciality] = cleaned_names
    return result


def load_project_rows(path: Path) -> list[dict[str, Any]]:
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
        subcontractors = row.get("subcontractors")
        if not project_id or not isinstance(project_name, str) or not project_name.strip():
            raise ValueError(f"Project seed row {row_number} must have project_id and project_name")
        if not isinstance(subcontractors, list) or not all(isinstance(name, str) and name.strip() for name in subcontractors):
            raise ValueError(f"Project seed row {row_number} subcontractors must be an array of non-empty names")
        if project_id in seen_projects:
            raise ValueError(f"Duplicate project_id in seed: {project_id}")
        seen_projects.add(project_id)
        names = [name.strip() for name in subcontractors]
        if len(names) != len(set(names)):
            raise ValueError(f"Project seed row {row_number} contains duplicate subcontractor assignments")
        rows.append({"project_id": project_id, "project_name": project_name.strip(), "subcontractors": names})
    return rows


def import_seed(
    db: Session,
    specialities: dict[str, list[str]],
    project_rows: list[dict[str, Any]],
    *,
    apply: bool = False,
) -> ImportSummary:
    project_names = {
        project_id: name
        for project_id, name in db.execute(text("SELECT id, name FROM app.project")).all()
    }
    speciality_rows = db.execute(text("SELECT id, name FROM app.speciality")).all()
    speciality_ids: dict[str, int] = {}
    for speciality_id, name in speciality_rows:
        if name in speciality_ids:
            raise ValueError(f"Database contains duplicate speciality name: {name!r}")
        speciality_ids[name] = speciality_id

    contractor_rows = db.execute(text("""
        SELECT sc.id, sc.name, s.name AS speciality
        FROM app.subcontractor sc
        JOIN app.speciality s ON s.id = sc.speciality_id
    """)).all()
    subcontractors_by_name: dict[str, tuple[int, str]] = {}
    for subcontractor_id, name, speciality in contractor_rows:
        if name in subcontractors_by_name:
            raise ValueError(f"Database contains duplicate subcontractor name: {name!r}")
        subcontractors_by_name[name] = (subcontractor_id, speciality)

    requested_speciality_by_name = {
        name: speciality
        for speciality, names in specialities.items()
        for name in names
    }
    for speciality, names in specialities.items():
        if speciality in speciality_ids:
            continue
        if apply:
            speciality_ids[speciality] = db.execute(
                text("INSERT INTO app.speciality (name) VALUES (:name) RETURNING id"),
                {"name": speciality},
            ).scalar_one()

    for name, speciality in requested_speciality_by_name.items():
        existing = subcontractors_by_name.get(name)
        if existing and existing[1] != speciality:
            raise ValueError(
                f"Subcontractor {name!r} already belongs to speciality {existing[1]!r}, expected {speciality!r}"
            )
        if existing:
            continue
        if apply:
            subcontractor_id = db.execute(
                text("""
                    INSERT INTO app.subcontractor (name, speciality_id)
                    VALUES (:name, :speciality_id) RETURNING id
                """),
                {"name": name, "speciality_id": speciality_ids[speciality]},
            ).scalar_one()
            subcontractors_by_name[name] = (subcontractor_id, speciality)

    for row in project_rows:
        existing_name = project_names.get(row["project_id"])
        if existing_name is None:
            raise ValueError(f"Project ID {row['project_id']!r} was not found in app.project")
        if existing_name != row["project_name"]:
            raise ValueError(
                f"Project ID/name mismatch for {row['project_id']!r}: seed={row['project_name']!r}, database={existing_name!r}"
            )
        for name in row["subcontractors"]:
            if name not in requested_speciality_by_name:
                raise ValueError(f"Subcontractor {name!r} is not defined in the speciality seed")

    current_links = {
        (project_id, name)
        for project_id, name in db.execute(text("""
            SELECT ps.project_id, sc.name
            FROM app.project_subcontractor ps
            JOIN app.subcontractor sc ON sc.id = ps.subcontractor_id
        """)).all()
    }
    desired_links = {
        (row["project_id"], name)
        for row in project_rows
        for name in row["subcontractors"]
    }
    links_to_insert = desired_links - current_links

    if apply:
        db.execute(
            text("""
                INSERT INTO app.project_subcontractor (project_id, subcontractor_id)
                VALUES (:project_id, :subcontractor_id)
                ON CONFLICT (project_id, subcontractor_id) DO NOTHING
            """),
            [
                {"project_id": project_id, "subcontractor_id": subcontractors_by_name[name][0]}
                for project_id, name in sorted(links_to_insert)
            ],
        )

    inserted_specialities = sum(name not in {row[1] for row in speciality_rows} for name in specialities)
    inserted_subcontractors = sum(name not in {row[1] for row in contractor_rows} for name in requested_speciality_by_name)
    return ImportSummary(
        specialities=len(specialities),
        subcontractors=len(requested_speciality_by_name),
        project_links=len(desired_links),
        specialities_inserted=inserted_specialities if apply else inserted_specialities,
        subcontractors_inserted=inserted_subcontractors if apply else inserted_subcontractors,
        project_links_inserted=len(links_to_insert),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specialities_json", type=Path, help="Speciality-to-subcontractor mapping JSON")
    parser.add_argument("project_links_json", type=Path, help="Project-to-subcontractor mapping JSON")
    parser.add_argument("--apply", action="store_true", help="Commit the inserts; without this flag, run a dry run")
    args = parser.parse_args()

    specialities = load_specialities(args.specialities_json)
    project_rows = load_project_rows(args.project_links_json)
    with SessionLocal.begin() as db:
        summary = import_seed(db, specialities, project_rows, apply=args.apply)

    action = "Applied" if args.apply else "Would insert"
    print(
        f"{action}: {summary.specialities_inserted} specialities, "
        f"{summary.subcontractors_inserted} subcontractors, "
        f"{summary.project_links_inserted} project links "
        f"(seed totals: {summary.specialities} specialities, "
        f"{summary.subcontractors} subcontractors, {summary.project_links} links)."
    )


if __name__ == "__main__":
    main()
