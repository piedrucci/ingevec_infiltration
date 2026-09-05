"""Controlled failure-cause catalog operations."""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FailureCause, FailureCauseAlias, FailureCauseCategory


def normalized_alias(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def canonical_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", normalized)).strip("_")


def create_failure_cause(
    db: Session,
    *,
    code: str,
    display_name_es: str,
    category_code: str,
    aliases: list[str],
) -> FailureCause:
    code = canonical_code(code)
    category_code = canonical_code(category_code)
    display_name_es = display_name_es.strip()
    if not code or not display_name_es:
        raise ValueError("Cause code and Spanish display name are required")
    category = db.scalar(select(FailureCauseCategory).where(FailureCauseCategory.code == category_code, FailureCauseCategory.is_active.is_(True)))
    if category is None:
        raise LookupError("Failure-cause category does not exist or is inactive")
    if db.scalar(select(FailureCause.id).where(FailureCause.code == code)) is not None:
        raise FileExistsError("A failure cause already uses that code")

    normalized_aliases = {normalized_alias(alias) for alias in [display_name_es, *aliases] if normalized_alias(alias)}
    existing_alias = db.scalar(select(FailureCauseAlias).where(FailureCauseAlias.normalized_alias.in_(normalized_aliases))) if normalized_aliases else None
    if existing_alias is not None:
        raise FileExistsError("One of the aliases already belongs to another failure cause")

    cause = FailureCause(code=code, display_name_es=display_name_es, category_id=category.id, is_active=True)
    db.add(cause)
    db.flush()
    for alias in sorted(normalized_aliases):
        db.add(FailureCauseAlias(failure_cause_id=cause.id, normalized_alias=alias))
    db.commit()
    db.refresh(cause)
    return cause
