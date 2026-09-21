import type { DashboardAssociationBreakdown, DashboardBreakdown } from "../../types";
import { Link } from "react-router-dom";
import { useDashboardSummary } from "../../queries/dashboard";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

const statusLabels: Record<string, string> = {
  UPLOADING: "Cargando", QUEUED: "En cola", PROCESSING: "Procesando", MATCHED: "Asociados",
  PENDING_REVIEW: "Requieren revisión", UNMATCHED: "Sin asociación", FAILED: "Con error", QUARANTINED: "En cuarentena",
};

function MetricCard({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return <article className="metric-card"><p>{label}</p><strong>{value}</strong>{detail && <span>{detail}</span>}</article>;
}

function BreakdownCard({ title, rows, total }: { title: string; rows: DashboardBreakdown[]; total: number }) {
  return <section className="card breakdown-card"><div className="section-title"><h2>{title}</h2><span>{rows.length} grupos</span></div>
    {rows.length ? <ul className="breakdown-list">{rows.map((row) => {
      const percent = total ? (row.count / total) * 100 : 0;
      return <li key={row.name}><div><span title={row.name}>{row.name}</span><strong>{row.count.toLocaleString("es-CL")} <small>({percent.toFixed(1)}%)</small></strong></div><div className="progress-track"><span style={{ width: `${percent}%` }} /></div></li>;
    })}</ul> : <p className="empty-state">Sin datos disponibles.</p>}
  </section>;
}

function ProjectManagerProgressCard({ rows }: { rows: DashboardAssociationBreakdown[] }) {
  return <section className="card project-manager-progress"><div className="section-title"><div><h2>Avance por gerente de proyecto</h2><p className="muted">Ítems conciliados mediante una o más causas</p></div><span>{rows.length} gerentes</span></div>
    {rows.length ? <div className="table-wrap"><table><thead><tr><th>Gerente de proyecto</th><th>Ítems</th><th>Conciliados</th><th>Pendientes</th><th>Avance</th><th>Con PDF</th></tr></thead><tbody>{rows.map((row) => <tr key={row.project_manager_id ?? "unassigned"}><td>{row.project_manager_id !== null ? <Link className="manager-link" to={`/project-managers/${row.project_manager_id}/items`}>{row.name}</Link> : row.name}</td><td>{row.items.toLocaleString("es-CL")}</td><td>{row.reconciled_items.toLocaleString("es-CL")}</td><td>{row.pending_reconciliation_items.toLocaleString("es-CL")}</td><td className="progress-cell"><div><strong>{(row.reconciliation_rate * 100).toFixed(1)}%</strong><div className="progress-track"><span style={{ width: `${row.reconciliation_rate * 100}%` }} /></div></div></td><td>{row.associated_items.toLocaleString("es-CL")}</td></tr>)}</tbody></table></div> : <p className="empty-state">Sin datos disponibles.</p>}
  </section>;
}

export function HomePage() {
  const summaryQuery = useDashboardSummary();
  const summary = summaryQuery.data;
  if (summaryQuery.isLoading) return <div className="loading-block"><LoadingIndicator label="Preparando resumen…" /></div>;
  if (!summary) return <ErrorMessage error={summaryQuery.error || new Error("No fue posible obtener el resumen.")} />;
  const { totals, breakdowns } = summary;
  const lastUpdated = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" }).format(new Date(summary.generated_at));

  return <>
    <section className="dashboard-heading"><div><p className="eyebrow">RESUMEN EJECUTIVO</p><h2>Estado de postventa</h2><p className="muted">Actualizado: {lastUpdated}</p></div>{summaryQuery.isFetching && <LoadingIndicator label="Actualizando…" compact />}</section>
    <section className="metric-grid">
      <MetricCard label="Ítems totales" value={totals.items.toLocaleString("es-CL")} />
      <MetricCard label="Ítems conciliados" value={totals.reconciled_items.toLocaleString("es-CL")} detail={`${(totals.reconciliation_rate * 100).toFixed(1)}% de avance`} />
      <MetricCard label="Pendientes de conciliación" value={totals.pending_reconciliation_items.toLocaleString("es-CL")} detail="Sin causas asignadas" />
      <MetricCard label="Cobertura documental" value={totals.associated_items.toLocaleString("es-CL")} detail={`${(totals.document_coverage_rate * 100).toFixed(1)}% con PDF`} />
      <MetricCard label="PDFs registrados" value={totals.documents.toLocaleString("es-CL")} />
    </section>
    <section className="card coverage-card"><div className="section-title"><h2>Avance de conciliación</h2><span>{(totals.reconciliation_rate * 100).toFixed(1)}%</span></div><div className="coverage-body"><div className="progress-track large"><span style={{ width: `${totals.reconciliation_rate * 100}%` }} /></div><p className="muted">{totals.reconciled_items.toLocaleString("es-CL")} conciliados · {totals.pending_reconciliation_items.toLocaleString("es-CL")} pendientes</p></div></section>
    <ProjectManagerProgressCard rows={summary.project_manager_association_progress ?? []} />
    <section className="dashboard-grid">
      <BreakdownCard title="Ítems por gerente divisional" rows={breakdowns.division_managers ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por gerente de proyecto" rows={breakdowns.project_managers ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por clasificación" rows={breakdowns.classifications ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por tipo" rows={breakdowns.item_types ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por subcontratista" rows={breakdowns.subcontractors ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por responsable" rows={breakdowns.handled_by ?? []} total={totals.items} />
      <BreakdownCard title="PDFs por estado" rows={Object.entries(totals.documents_by_status).map(([name, count]) => ({ name: statusLabels[name] ?? name, count }))} total={totals.documents} />
    </section>
  </>;
}
