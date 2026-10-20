"""Read-only failure-cause group catalog queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FailureCause, FailureCauseCategory, FailureCauseCategoryGroupLink, FailureCauseCategoryLink, FailureCauseGroup


def list_groups(db: Session) -> list[FailureCauseGroup]:
    return list(db.scalars(select(FailureCauseGroup).order_by(FailureCauseGroup.display_name_es, FailureCauseGroup.code)).all())


def list_group_categories(db: Session, group_code: str) -> list[FailureCauseCategory]:
    group_id = db.scalar(select(FailureCauseGroup.id).where(FailureCauseGroup.code == group_code))
    if group_id is None:
        raise LookupError("Failure-cause group not found")
    return list(db.scalars(
        select(FailureCauseCategory)
        .join(FailureCauseCategoryGroupLink, FailureCauseCategoryGroupLink.category_id == FailureCauseCategory.id)
        .where(FailureCauseCategoryGroupLink.group_id == group_id)
        .order_by(FailureCauseCategory.display_name_es, FailureCauseCategory.code)
    ).all())


def list_group_category_causes(db: Session, group_code: str, category_code: str) -> list[FailureCause]:
    """Causes assigned to this exact group and category; unassigned causes are not listed."""
    pair = db.execute(
        select(FailureCauseGroup.id, FailureCauseCategory.id)
        .join(FailureCauseCategoryGroupLink, FailureCauseCategoryGroupLink.group_id == FailureCauseGroup.id)
        .join(FailureCauseCategory, FailureCauseCategory.id == FailureCauseCategoryGroupLink.category_id)
        .where(FailureCauseGroup.code == group_code, FailureCauseCategory.code == category_code)
    ).first()
    if pair is None:
        raise LookupError("Group or category not found")
    group_id, category_id = pair
    return list(db.scalars(
        select(FailureCause)
        .join(FailureCauseCategoryLink, FailureCauseCategoryLink.failure_cause_id == FailureCause.id)
        .where(FailureCauseCategoryLink.category_id == category_id, FailureCauseCategoryLink.group_id == group_id)
        .order_by(FailureCause.display_name_es, FailureCause.code)
    ).all())
