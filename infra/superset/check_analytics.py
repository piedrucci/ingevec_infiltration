"""Read-only health check of Superset analytics datasets, charts and dashboards.

Run inside the Superset container after analytics migrations:
    python /app/pythonpath/ingevec/check_analytics.py [RETIRED_VALUE ...]

Checks, through Superset's analytics connection (superset_reader): dataset columns against the live
views, every dataset metric, every saved chart query, and chart/dashboard references to retired values
(e.g. split cause codes or renamed causes). Exits 1 if anything is broken. Admin execution bypasses
row-level security, so viewer scope must still be checked with a non-admin account.
"""

import json
import re
import sys

from flask import g
from sqlalchemy import text

from superset.app import create_app

# Values removed by the cause-group assignment (migration 20261019_0025) and the item-type drop (0024).
DEFAULT_RETIRED = ["BROKEN_SEALS__WINDOWS", "BROKEN_SEALS__SHEET_METAL", "DESPICHE_TAPADO", "AREA_SIN_IMPERM",
                   "Daño de gorro chino", "Area sin impermeabilización ", "tipo_item", "item_type"]


def _references(blob: str, retired: list[str]) -> list[str]:
    # A retired code must not match its group-specific successors (e.g. CODE__EJECUCION).
    return [value for value in retired if re.search(r"(?<![A-Za-z_])" + re.escape(value) + r"(?!__|[A-Za-z_])", blob)]


def main() -> int:
    retired = sys.argv[1:] or DEFAULT_RETIRED
    problems = 0
    app = create_app()
    with app.app_context(), app.test_request_context():
        from superset import db, security_manager
        from superset.charts.schemas import ChartDataQueryContextSchema
        from superset.commands.chart.data.get_data_command import ChartDataCommand
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        print("== Datasets")
        for dataset in db.session.query(SqlaTable).order_by(SqlaTable.id):
            name = f"{dataset.schema}.{dataset.table_name}"
            try:
                with dataset.database.get_sqla_engine() as engine, engine.connect() as connection:
                    live = {row[0] for row in connection.execute(text(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :t"),
                        {"s": dataset.schema, "t": dataset.table_name})}
                    rows = connection.execute(text(f"SELECT count(*) FROM {name}")).scalar()
                    stored = {column.column_name for column in dataset.columns if not column.expression}
                    missing, unregistered = sorted(stored - live), sorted(live - stored)
                    print(f"{name}: {rows} rows; missing in view: {missing or 'none'}; not in dataset: {unregistered or 'none'}")
                    problems += bool(missing)
                    # Window metrics (cumulative share) need a grouping, as in a chart.
                    group_column = "codigo_causa_falla" if "codigo_causa_falla" in live else sorted(live)[0]
                    for metric in dataset.metrics:
                        windowed = " OVER " in metric.expression.upper()
                        sql = f"SELECT {metric.expression} FROM {name}" + (f" GROUP BY {group_column} LIMIT 1" if windowed else "")
                        try:
                            connection.execute(text(sql)).scalar()
                            print(f"  metric {metric.metric_name}: OK")
                        except Exception as exc:  # noqa: BLE001 - report every failing metric
                            problems += 1
                            print(f"  metric {metric.metric_name}: ERROR {str(exc).splitlines()[0]}")
            except Exception as exc:  # noqa: BLE001
                problems += 1
                print(f"{name}: ERROR {str(exc).splitlines()[0]}")

        print("\n== Charts")
        admin = next((u for u in security_manager.get_all_users() if any(r.name == "Admin" for r in u.roles)), None)
        if admin is None:
            print("No Admin user found; cannot execute charts")
            return 1
        g.user = admin
        for chart in db.session.query(Slice).order_by(Slice.id):
            refs = _references((chart.params or "") + (chart.query_context or ""), retired)
            problems += bool(refs)
            label = f"chart {chart.id} {chart.slice_name!r} (dataset {chart.datasource_id})"
            if not chart.query_context:
                print(f"{label}: NOT EXECUTED (no saved query; open and save it once in Explore); retired refs: {refs or 'none'}")
                continue
            try:
                command = ChartDataCommand(ChartDataQueryContextSchema().load(json.loads(chart.query_context)))
                command.validate()
                queries = command.run()["queries"]
                errors = [query["error"] for query in queries if query.get("error")]
                problems += bool(errors)
                status = f"ERROR {errors}" if errors else f"OK rows={[query.get('rowcount') for query in queries]}"
            except Exception as exc:  # noqa: BLE001
                problems += 1
                status = f"ERROR {type(exc).__name__}: {str(exc)[:200]}"
            print(f"{label}: {status}; retired refs: {refs or 'none'}")

        print("\n== Dashboards")
        for dashboard in db.session.query(Dashboard).order_by(Dashboard.id):
            metadata = dashboard.json_metadata or "{}"
            filters = json.loads(metadata).get("native_filter_configuration", [])
            refs = _references(metadata + (dashboard.position_json or ""), retired)
            problems += bool(refs)
            targets = [(f.get("name"), [t.get("column", {}).get("name") for t in f.get("targets", [])]) for f in filters]
            print(f"{dashboard.dashboard_title!r} (published={dashboard.published}): charts={[s.id for s in dashboard.slices]}; "
                  f"native filters={targets}; retired refs: {refs or 'none'}")

    print(f"\n{'OK: no problems found' if not problems else f'PROBLEMS: {problems}'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
