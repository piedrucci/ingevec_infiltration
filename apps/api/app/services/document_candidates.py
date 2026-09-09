"""Resolve PDF project metadata and build manual-review candidates."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import DocumentPostventaItem, PostventaItem, Project


def normalize_project_identifier(value: str | None) -> str:
    """Return a stable identifier for values such as ``712`` and ``712.0``."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    if normalized.endswith("0") and ".0" in str(value):
        normalized = normalized[:-1]
    return normalized


def normalize_project_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def _name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_terms, right_terms = set(left.split()), set(right.split())
    token_score = len(left_terms & right_terms) / len(left_terms | right_terms) if left_terms and right_terms else 0.0
    return max(token_score, SequenceMatcher(None, left, right).ratio())


@dataclass(frozen=True)
class ProjectMatch:
    project: Project
    method: str
    score: float


@dataclass(frozen=True)
class CandidateSet:
    items: list[PostventaItem]
    project_names: dict[str, str]
    project_match_method: str | None
    project_match_score: float
    project_match_message: str


def resolve_projects(db: Session, project_number: str | None, project_name: str | None) -> list[ProjectMatch]:
    """Resolve the PDF project, giving identifiers precedence over names."""
    projects = db.scalars(select(Project)).all()
    identifier = normalize_project_identifier(project_number)
    if identifier:
        exact = [project for project in projects if normalize_project_identifier(project.id) == identifier]
        if exact:
            return [ProjectMatch(project, "id", 1.0) for project in exact]
        prefix = [project for project in projects if normalize_project_identifier(project.id).startswith(identifier)]
        if len(prefix) == 1:
            return [ProjectMatch(prefix[0], "id", 0.95)]

    name = normalize_project_name(project_name)
    if name:
        matches = [
            ProjectMatch(project, "name", _name_similarity(name, normalize_project_name(project.name)))
            for project in projects
        ]
        strong = [match for match in matches if match.score >= 0.80]
        if strong:
            best_score = max(match.score for match in strong)
            return [match for match in strong if match.score >= best_score - 0.03]
    return []


def find_document_candidates(
    db: Session,
    *,
    project_number: str | None,
    project_name: str | None,
    location: str | None = None,
) -> CandidateSet:
    matches = resolve_projects(db, project_number, project_name)
    if not matches:
        return CandidateSet([], {}, None, 0.0, "No se pudo identificar el proyecto por número ni nombre.")

    project_ids = [match.project.id for match in matches]
    associated = exists(
        select(DocumentPostventaItem.postventa_item_id).where(
            DocumentPostventaItem.postventa_item_id == PostventaItem.id
        )
    )
    items = db.scalars(
        select(PostventaItem)
        .where(PostventaItem.project_id.in_(project_ids))
        .where(~associated)
        .order_by(PostventaItem.id)
    ).all()
    method = "id" if all(match.method == "id" for match in matches) else "name"
    score = max(match.score for match in matches)
    if not items:
        message = "El proyecto fue identificado, pero no tiene ítems sin asociación."
    else:
        message = f"{len(items)} ítems sin asociación encontrados por {('número de obra' if method == 'id' else 'nombre de proyecto')}."
    return CandidateSet(items, {project.id: project.name for project in (match.project for match in matches)}, method, score, message)
