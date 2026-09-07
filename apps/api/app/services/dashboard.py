"""Read-model queries used by the administrative home dashboard."""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import DashboardAssociationBreakdown, DashboardBreakdown, DashboardSummary, DashboardTotals
from app.services.dashboard_cache import dashboard_cache_version, get_dashboard_summary, set_dashboard_summary


_SUMMARY_SQL = text("""
WITH base AS (
  SELECT
    pi.id,
    COALESCE(NULLIF(BTRIM(dm.name), ''), 'Sin asignar') AS division_manager,
    COALESCE(NULLIF(BTRIM(pm.name), ''), 'Sin asignar') AS project_manager,
    COALESCE(NULLIF(BTRIM(c.name), ''), 'Sin asignar') AS classification,
    COALESCE(NULLIF(BTRIM(it.name), ''), 'Sin asignar') AS item_type,
    COALESCE(NULLIF(BTRIM(sc.name), ''), 'Sin asignar') AS subcontractor,
    COALESCE(NULLIF(BTRIM(pi.handled_by), ''), 'Sin asignar') AS handled_by,
    (dpi.postventa_item_id IS NOT NULL) AS is_associated
  FROM app.postventa_item pi
  JOIN app.project p ON p.id = pi.project_id
  LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
  LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
  LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
  JOIN app.classification c ON c.id = pi.classification_id
  JOIN app.item_type it ON it.id = pi.item_type_id
  LEFT JOIN app.subcontractor sc ON sc.id = pi.subcontractor_id
  LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
),
documents AS (SELECT status, COUNT(*)::int AS count FROM app.document GROUP BY status)
SELECT jsonb_build_object(
  'totals', jsonb_build_object(
    'items', (SELECT COUNT(*)::int FROM base),
    'associated_items', (SELECT COUNT(*)::int FROM base WHERE is_associated),
    'pending_items', (SELECT COUNT(*)::int FROM base WHERE NOT is_associated),
    'documents', (SELECT COUNT(*)::int FROM app.document),
    'documents_by_status', COALESCE((SELECT jsonb_object_agg(status, count) FROM documents), '{}'::jsonb)
  ),
  'breakdowns', jsonb_build_object(
    'division_managers', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT division_manager AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'project_managers', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT project_manager AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'classifications', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT classification AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'item_types', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT item_type AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'subcontractors', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT subcontractor AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb),
    'handled_by', COALESCE((SELECT jsonb_agg(jsonb_build_object('name', name, 'count', count) ORDER BY count DESC, name) FROM (SELECT handled_by AS name, COUNT(*)::int AS count FROM base GROUP BY 1) grouped), '[]'::jsonb)
  ),
  'project_manager_association_progress', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'name', name,
      'items', items,
      'associated_items', associated_items,
      'pending_items', items - associated_items,
      'association_rate', CASE WHEN items > 0 THEN associated_items::numeric / items ELSE 0 END
    ) ORDER BY (items - associated_items) DESC, name)
    FROM (
      SELECT project_manager AS name, COUNT(*)::int AS items,
        COUNT(*) FILTER (WHERE is_associated)::int AS associated_items
      FROM base GROUP BY project_manager
    ) grouped
  ), '[]'::jsonb)
) AS summary
""")


def dashboard_summary(db: Session) -> DashboardSummary:
    version = dashboard_cache_version()
    cached = get_dashboard_summary(version)
    if cached is not None:
        return DashboardSummary.model_validate(cached)

    raw = db.scalar(_SUMMARY_SQL) or {"totals": {}, "breakdowns": {}}
    totals = raw["totals"]
    items = totals["items"]
    associated = totals["associated_items"]
    result = DashboardSummary(
        generated_at=datetime.now(timezone.utc),
        totals=DashboardTotals(
            items=items,
            associated_items=associated,
            pending_items=totals["pending_items"],
            association_rate=(associated / items) if items else 0,
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
