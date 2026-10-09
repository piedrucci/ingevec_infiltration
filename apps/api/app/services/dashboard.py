"""Read-model queries used by the administrative home dashboard."""

from datetime import datetime, timezone

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.models import PostventaItem, PostventaItemFailureCause, Project
from app.schemas import DashboardAssociationBreakdown, DashboardBreakdown, DashboardProjectProgress, DashboardProjectProgressResponse, DashboardSummary, DashboardSubcontractorBreakdown, DashboardSubcontractorProject, DashboardTotals, PageMeta
from app.services.dashboard_cache import dashboard_cache_version, get_dashboard_summary, set_dashboard_summary


_SUMMARY_SQL = text("""
WITH base AS (
  SELECT
    pi.id,
    pm.id AS project_manager_id,
    COALESCE(NULLIF(BTRIM(dm.name), ''), 'Sin asignar') AS division_manager,
    COALESCE(NULLIF(BTRIM(pm.name), ''), 'Sin asignar') AS project_manager,
    COALESCE(NULLIF(BTRIM(c.name), ''), 'Sin asignar') AS classification,
    COALESCE(NULLIF(BTRIM(pi.handled_by), ''), 'Sin asignar') AS handled_by,
    EXISTS (
      SELECT 1
      FROM app.document_postventa_item dpi
      WHERE dpi.postventa_item_id = pi.id
    ) AS has_document,
    EXISTS (
      SELECT 1
      FROM app.postventa_item_failure_cause pifc
      WHERE pifc.postventa_item_id = pi.id
    ) AS is_reconciled
  FROM app.postventa_item pi
  JOIN app.project p ON p.id = pi.project_id
  LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
  LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
  LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
  JOIN app.classification c ON c.id = pi.classification_id
),
documents AS (SELECT status, COUNT(*)::int AS count FROM app.document GROUP BY status)
SELECT jsonb_build_object(
  'totals', jsonb_build_object(
    'items', (SELECT COUNT(*)::int FROM base),
    'associated_items', (SELECT COUNT(*)::int FROM base WHERE has_document),
    'pending_items', (SELECT COUNT(*)::int FROM base WHERE NOT has_document),
    'reconciled_items', (SELECT COUNT(*)::int FROM base WHERE is_reconciled),
    'pending_reconciliation_items', (SELECT COUNT(*)::int FROM base WHERE NOT is_reconciled),
    'documents', (SELECT COUNT(*)::int FROM app.document),
    'documents_by_status', COALESCE((SELECT jsonb_object_agg(status, count) FROM documents), '{}'::jsonb)
  ),
  'breakdowns', jsonb_build_object(
    'division_managers', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT division_manager AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'project_managers', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT project_manager AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'classifications', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT classification AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'failure_cause_categories', COALESCE((
      SELECT jsonb_agg(jsonb_build_object('name', name, 'code', code, 'count', count) ORDER BY count DESC, name)
      FROM (
        -- Multiple causes in the same category count as one item.
        SELECT fcc.display_name_es AS name, fcc.code AS code, COUNT(DISTINCT pifc.postventa_item_id)::int AS count
        FROM app.postventa_item_failure_cause pifc
        JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = pifc.failure_cause_id
        JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
        GROUP BY fcc.id, fcc.display_name_es
      ) grouped
    ), '[]'::jsonb),
    'handled_by', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT handled_by AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb)
  ),
  'project_manager_association_progress', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'project_manager_id', project_manager_id,
      'name', name,
      'items', items,
      'associated_items', documented_items,
      'pending_items', items - documented_items,
      'association_rate', CASE WHEN items > 0 THEN documented_items::numeric / items ELSE 0 END,
      'reconciled_items', reconciled_items,
      'pending_reconciliation_items', items - reconciled_items,
      'reconciliation_rate', CASE WHEN items > 0 THEN reconciled_items::numeric / items ELSE 0 END,
      'document_coverage_rate', CASE WHEN items > 0 THEN documented_items::numeric / items ELSE 0 END
    ) ORDER BY (items - reconciled_items) DESC, name)
    FROM (
      SELECT project_manager_id, project_manager AS name, COUNT(*)::int AS items,
        COUNT(*) FILTER (WHERE has_document)::int AS documented_items,
        COUNT(*) FILTER (WHERE is_reconciled)::int AS reconciled_items
      FROM base GROUP BY project_manager_id, project_manager
    ) grouped
  ), '[]'::jsonb)
) AS summary
""")

_SUBCONTRACTORS_SQL = text("""
SELECT sc.id, sc.name, s.name AS speciality, COUNT(DISTINCT ps.project_id)::int AS project_count
FROM app.subcontractor sc
JOIN app.speciality s ON s.id = sc.speciality_id
LEFT JOIN app.project_subcontractor ps ON ps.subcontractor_id = sc.id
GROUP BY sc.id, sc.name, s.name
ORDER BY project_count DESC, sc.name
""")


def dashboard_subcontractors(db: Session) -> list[DashboardSubcontractorBreakdown]:
    rows = db.execute(_SUBCONTRACTORS_SQL).mappings()
    return [DashboardSubcontractorBreakdown.model_validate(row) for row in rows]


_SUBCONTRACTOR_PROJECTS_SQL = text("""
SELECT p.id AS project_id, p.name AS project_name
FROM app.project_subcontractor ps
JOIN app.project p ON p.id = ps.project_id
WHERE ps.subcontractor_id = :subcontractor_id
ORDER BY p.id
""")


def dashboard_subcontractor_projects(db: Session, subcontractor_id: int) -> list[DashboardSubcontractorProject]:
    rows = db.execute(_SUBCONTRACTOR_PROJECTS_SQL, {"subcontractor_id": subcontractor_id}).mappings()
    return [DashboardSubcontractorProject.model_validate(row) for row in rows]


def dashboard_project_progress(db: Session, *, limit: int, offset: int, sort_by: str, sort_direction: str) -> DashboardProjectProgressResponse:
    has_cause = select(PostventaItemFailureCause.postventa_item_id).where(
        PostventaItemFailureCause.postventa_item_id == PostventaItem.id
    ).exists()
    item_count = func.count(PostventaItem.id)
    conciliated_count = func.count(PostventaItem.id).filter(has_cause)
    pending_count = func.count(PostventaItem.id).filter(~has_cause)
    percentage = case(
        (item_count > 0, conciliated_count * 100.0 / item_count),
        else_=0.0,
    )
    sort_columns = {
        "name": Project.name,
        "items": item_count,
        "conciliated": conciliated_count,
        "pending": pending_count,
        "percentage": percentage,
    }
    if sort_by not in sort_columns:
        raise ValueError("Invalid project progress sort column")
    if sort_direction not in {"asc", "desc"}:
        raise ValueError("Invalid project progress sort direction")

    total = db.scalar(select(func.count()).select_from(Project)) or 0
    sort_column = sort_columns[sort_by]
    primary_order = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    if sort_by == "items":
        order = [primary_order, conciliated_count.desc(), percentage.desc(), Project.name.asc(), Project.id.asc()]
    elif sort_by == "percentage":
        order = [primary_order, item_count.desc(), Project.name.asc(), Project.id.asc()]
    elif sort_by == "name":
        order = [primary_order, item_count.desc(), percentage.desc(), Project.id.asc()]
    else:
        order = [primary_order, Project.name.asc(), item_count.desc(), percentage.desc(), Project.id.asc()]
    rows = db.execute(
        select(
            Project.id.label("project_id"),
            Project.name,
            item_count.label("items"),
            conciliated_count.label("conciliated"),
            pending_count.label("pending"),
            percentage.label("percentage"),
        )
        .outerjoin(PostventaItem, PostventaItem.project_id == Project.id)
        .group_by(Project.id, Project.name)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    ).mappings()
    return DashboardProjectProgressResponse(
        items=[DashboardProjectProgress.model_validate(row) for row in rows],
        page=PageMeta(total=total, limit=limit, offset=offset),
    )


def dashboard_summary(db: Session) -> DashboardSummary:
    version = dashboard_cache_version()
    cached = get_dashboard_summary(version)
    if cached is not None:
        return DashboardSummary.model_validate(cached)

    raw = db.scalar(_SUMMARY_SQL) or {"totals": {}, "breakdowns": {}}
    totals = raw["totals"]
    items = totals["items"]
    documented = totals["associated_items"]
    reconciled = totals["reconciled_items"]
    result = DashboardSummary(
        generated_at=datetime.now(timezone.utc),
        totals=DashboardTotals(
            items=items,
            associated_items=documented,
            pending_items=totals["pending_items"],
            association_rate=(documented / items) if items else 0,
            reconciled_items=reconciled,
            pending_reconciliation_items=totals["pending_reconciliation_items"],
            reconciliation_rate=(reconciled / items) if items else 0,
            document_coverage_rate=(documented / items) if items else 0,
            documents=totals["documents"],
            documents_by_status=totals["documents_by_status"],
        ),
        breakdowns={key: [DashboardBreakdown.model_validate(row) for row in rows] for key, rows in raw["breakdowns"].items()},
        project_manager_association_progress=[
            DashboardAssociationBreakdown.model_validate(row)
            for row in raw["project_manager_association_progress"]
        ],
    )
    set_dashboard_summary(version, result.model_dump(mode="json"))
    return result
