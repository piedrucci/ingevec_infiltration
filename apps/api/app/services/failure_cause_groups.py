"""Read-only failure-cause group catalog queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FailureCauseCategory, FailureCauseCategoryGroupLink, FailureCauseGroup


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
