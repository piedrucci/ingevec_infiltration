import { Link, useLocation } from "react-router-dom";
import { useMemo } from "react";
import type { ColumnDef, SortingState, StockFeatures } from "@tanstack/react-table";

import { useEvaluationItems } from "../../queries/postventa-items";
import type { PostventaItem } from "../../types";
import { ErrorMessage, LoadingIndicator } from "../documents/components";
import { useEvaluationSearchParams } from "./useEvaluationSearchParams";
import { DataTable } from "../../components/DataTable";

const PAGE_SIZE = 50;

export function ItemsEvaluationPage() {
  const location = useLocation();
  const { params, updateParams } = useEvaluationSearchParams();
  const { search, reconciliationStatus, documentFilter, offset, sortBy, sortDirection } = params;
  const itemsQuery = useEvaluationItems({
    search,
    reconciliationStatus: reconciliationStatus || undefined,
    hasDocument: documentFilter === "" ? undefined : documentFilter === "true",
    limit: PAGE_SIZE,
    offset,
    sortBy,
    sortDirection,
  });
  const items = itemsQuery.data?.items ?? [];
  const total = itemsQuery.data?.page.total ?? 0;
  const itemColumns = useMemo<ColumnDef<StockFeatures, PostventaItem, unknown>[]>(() => [
    { accessorKey: "project_id", header: "Obra" },
    { accessorKey: "notes", header: "Observación" },
    {
      id: "causes",
      header: "Causas",
      enableSorting: false,
      cell: ({ row }) => row.original.failure_causes.length
        ? row.original.failure_causes.map((cause) => <span className="cause-tag" key={cause.code}>{cause.display_name_es}</span>)
        : "Sin causas",
    },
    {
      id: "reconciliation_status",
      header: "Estado",
      cell: ({ row }) => {
        const reconciled = row.original.reconciliation_status === "RECONCILED";
        return <span className={`reconciliation-status ${reconciled ? "reconciliation-status-reconciled" : "reconciliation-status-pending"}`}>{reconciled ? "Conciliado" : "Pendiente"}</span>;
      },
    },
    { id: "pdf", header: "PDF", enableSorting: false, cell: ({ row }) => row.original.has_document ? "Sí" : "No" },
    {
      id: "action",
      header: "",
      enableSorting: false,
      cell: ({ row }) => {
        const reconciled = row.original.reconciliation_status === "RECONCILED";
        const actionLabel = reconciled ? "Editar causas" : "Evaluar ítem";
        return <Link className="icon-action-link" aria-label={actionLabel} title={actionLabel} to={`/items/${row.original.public_id}/evaluation?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`}>{reconciled ? <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M4 16.5V20h3.5L18 9.5 14.5 6 4 16.5Z" /><path d="m13.5 7 3.5 3.5" /></svg> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M9 5h6" /><path d="M9 3h6v4H9z" /><path d="M6 5H4v16h16V5h-2" /><path d="m8 13 2 2 5-5" /></svg>}</Link>;
      },
    },
  ], [location.pathname, location.search]);
  const sorting: SortingState = [{ id: sortBy, desc: sortDirection === "desc" }];

  return <>
    <section className="dashboard-heading"><div><p className="eyebrow">EVALUACIÓN MANUAL</p><h2>Conciliación de ítems</h2><p className="muted">Asigna una o más causas a un ítem, aun cuando no tenga PDF.</p></div><span>{total.toLocaleString("es-CL")} ítems</span></section>
    <section className="card">
      <div className="filters evaluation-filters">
        <label>Buscar<input value={search} onChange={(event) => updateParams({ search: event.target.value })} placeholder="Obra, proyecto u observación" /></label>
        <label>Estado<select value={reconciliationStatus || "ALL"} onChange={(event) => updateParams({ reconciliationStatus: event.target.value === "ALL" ? "" : event.target.value as "PENDING" | "RECONCILED" })}><option value="ALL">Todos</option><option value="PENDING">Pendientes</option><option value="RECONCILED">Conciliados</option></select></label>
        <label>PDF<select value={documentFilter} onChange={(event) => updateParams({ documentFilter: event.target.value as "" | "true" | "false" })}><option value="">Todos</option><option value="true">Con PDF</option><option value="false">Sin PDF</option></select></label>
      </div>
      <ErrorMessage error={itemsQuery.error} />
      {itemsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando ítems…" /></div>}
      <DataTable data={items} columns={itemColumns} sorting={sorting} onSortingChange={(updater) => { const next = typeof updater === "function" ? updater(sorting) : updater; const first = next[0]; const nextSort = first?.id === "notes" || first?.id === "reconciliation_status" || first?.id === "project_id" ? first.id : "project_id"; updateParams({ sortBy: nextSort, sortDirection: first?.desc ? "desc" : "asc" }); }} getRowId={(item) => item.public_id} emptyMessage="No hay ítems para los filtros seleccionados." />
      <div className="pagination"><button className="secondary" type="button" disabled={!offset || itemsQuery.isFetching} onClick={() => updateParams({ offset: Math.max(0, offset - PAGE_SIZE) })}>Anterior</button><span>{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${total}` : "0 ítems"}</span><button className="secondary" type="button" disabled={offset + PAGE_SIZE >= total || itemsQuery.isFetching} onClick={() => updateParams({ offset: offset + PAGE_SIZE })}>Siguiente</button></div>
    </section>
  </>;
}
