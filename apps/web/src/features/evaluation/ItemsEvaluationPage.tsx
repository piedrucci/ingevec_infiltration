import { Link } from "react-router-dom";
import { useState } from "react";

import { useEvaluationItems } from "../../queries/postventa-items";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

const PAGE_SIZE = 50;

export function ItemsEvaluationPage() {
  const [search, setSearch] = useState("");
  const [reconciliationStatus, setReconciliationStatus] = useState<"" | "PENDING" | "RECONCILED">("PENDING");
  const [documentFilter, setDocumentFilter] = useState<"" | "true" | "false">("");
  const [offset, setOffset] = useState(0);
  const itemsQuery = useEvaluationItems({
    search,
    reconciliationStatus: reconciliationStatus || undefined,
    hasDocument: documentFilter === "" ? undefined : documentFilter === "true",
    limit: PAGE_SIZE,
    offset,
  });
  const items = itemsQuery.data?.items ?? [];
  const total = itemsQuery.data?.page.total ?? 0;

  return <>
    <section className="dashboard-heading"><div><p className="eyebrow">EVALUACIÓN MANUAL</p><h2>Conciliación de ítems</h2><p className="muted">Asigna una o más causas a un ítem, aun cuando no tenga PDF.</p></div><span>{total.toLocaleString("es-CL")} ítems</span></section>
    <section className="card">
      <div className="filters evaluation-filters">
        <label>Buscar<input value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} placeholder="Obra, proyecto u observación" /></label>
        <label>Estado<select value={reconciliationStatus} onChange={(event) => { setReconciliationStatus(event.target.value as "" | "PENDING" | "RECONCILED"); setOffset(0); }}><option value="">Todos</option><option value="PENDING">Pendientes</option><option value="RECONCILED">Conciliados</option></select></label>
        <label>PDF<select value={documentFilter} onChange={(event) => { setDocumentFilter(event.target.value as "" | "true" | "false"); setOffset(0); }}><option value="">Todos</option><option value="true">Con PDF</option><option value="false">Sin PDF</option></select></label>
      </div>
      <ErrorMessage error={itemsQuery.error} />
      {itemsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando ítems…" /></div>}
      <div className="table-wrap"><table><thead><tr><th>Obra</th><th>Observación</th><th>Causas</th><th>Estado</th><th>PDF</th><th /></tr></thead><tbody>
        {items.map((item) => {
          const reconciled = item.reconciliation_status === "RECONCILED";
          const actionLabel = reconciled ? "Editar causas" : "Evaluar ítem";
          return <tr key={item.public_id}><td>{item.project_id}</td><td>{item.notes}</td><td>{item.failure_causes.length ? item.failure_causes.map((cause) => <span className="cause-tag" key={cause.code}>{cause.display_name_es}</span>) : "Sin causas"}</td><td><span className={`reconciliation-status ${reconciled ? "reconciliation-status-reconciled" : "reconciliation-status-pending"}`}>{reconciled ? "Conciliado" : "Pendiente"}</span></td><td>{item.has_document ? "Sí" : "No"}</td><td><Link className="icon-action-link" aria-label={actionLabel} title={actionLabel} to={`/items/${item.public_id}/evaluation`}>{reconciled ? <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M4 16.5V20h3.5L18 9.5 14.5 6 4 16.5Z" /><path d="m13.5 7 3.5 3.5" /></svg> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M9 5h6" /><path d="M9 3h6v4H9z" /><path d="M6 5H4v16h16V5h-2" /><path d="m8 13 2 2 5-5" /></svg>}</Link></td></tr>;
        })}
        {!itemsQuery.isLoading && !items.length && <tr><td colSpan={6}>No hay ítems para los filtros seleccionados.</td></tr>}
      </tbody></table></div>
      <div className="pagination"><button className="secondary" type="button" disabled={!offset || itemsQuery.isFetching} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>Anterior</button><span>{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${total}` : "0 ítems"}</span><button className="secondary" type="button" disabled={offset + PAGE_SIZE >= total || itemsQuery.isFetching} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Siguiente</button></div>
    </section>
  </>;
}
