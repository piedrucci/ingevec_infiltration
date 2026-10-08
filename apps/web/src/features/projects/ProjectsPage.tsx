import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ColumnDef, StockFeatures } from "@tanstack/react-table";

import { usePostventaItems } from "../../queries/postventa-items";
import { useProjects } from "../../queries/projects";
import type { PostventaItem } from "../../types";
import { ErrorMessage, LoadingIndicator, ReconciliationBadge } from "../documents/components";
import { useUrlSearchParams } from "../evaluation/useEvaluationSearchParams";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { SearchableSelect } from "../../components/ui/searchable-select";

const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat("es-CL").format(new Date(`${value}T00:00:00`)) : "-";
const ITEM_PAGE_SIZE = 20;

export function ProjectsPage() {
  const location = useLocation();
  const { searchParams, updateUrlParams } = useUrlSearchParams();
  const selectedProjectId = searchParams.get("project");
  const itemSearch = searchParams.get("item_q") ?? "";
  const requestedItemOffset = Number(searchParams.get("item_offset") ?? "0");
  const itemOffset = Number.isSafeInteger(requestedItemOffset) && requestedItemOffset >= 0 ? requestedItemOffset : 0;
  const itemSortBy = "notes" as const;
  const itemSortDirection = searchParams.get("item_dir") === "desc" ? "desc" : "asc";
  const projectOptionsQuery = useProjects({ limit: 100, offset: 0, sortBy: "id", sortDirection: "asc" });
  const projectOptions = [
    { value: "__none__", label: "Selecciona un proyecto" },
    ...(projectOptionsQuery.data?.items ?? []).map((project) => ({ value: project.id, label: `${project.id} · ${project.name}` })),
  ];
  const selectedProject = projectOptionsQuery.data?.items.find((project) => project.id === selectedProjectId)
    ?? null;
  const itemsQuery = usePostventaItems(selectedProject?.id ?? null, itemSearch, { limit: ITEM_PAGE_SIZE, offset: itemOffset, sortBy: itemSortBy, sortDirection: itemSortDirection });
  const items = itemsQuery.data?.items ?? [];
  const totalItems = itemsQuery.data?.page.total ?? 0;

  const itemColumns = useMemo<ColumnDef<StockFeatures, PostventaItem, unknown>[]>(() => [
    {
      accessorKey: "notes",
      header: "Observación",
      cell: ({ row }) => <span className="project-item-observation" title={row.original.notes}>{row.original.notes}</span>,
    },
    {
      id: "causes",
      header: "Causas",
      enableSorting: false,
      cell: ({ row }) => row.original.failure_causes.length
        ? row.original.failure_causes.map((cause) => <span className="mr-1 mb-1 inline-block" key={cause.code}><Badge variant="secondary">{cause.category_name_es ? `${cause.category_name_es} · ${cause.display_name_es}` : cause.display_name_es}</Badge></span>)
        : "Sin causa",
    },
    {
      id: "status",
      header: "Estado",
      enableSorting: false,
      cell: ({ row }) => {
        const reconciled = row.original.reconciliation_status === "RECONCILED";
        return <ReconciliationBadge reconciled={reconciled} />;
      },
    },
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
  return <>
    <Card className="project-selector-card gap-3 py-4">
      <CardHeader className="px-5"><CardTitle>Buscar proyecto</CardTitle></CardHeader>
      <CardContent className="px-5"><SearchableSelect id="project-select" value={selectedProjectId ?? "__none__"} options={projectOptions} onValueChange={(value) => updateUrlParams({ project: value === "__none__" ? null : value, item_offset: 0 })} placeholder="Buscar por obra o nombre…" searchPlaceholder="Buscar proyecto por obra o nombre" /></CardContent>
    </Card>
    <ErrorMessage error={projectOptionsQuery.error ?? itemsQuery.error} />
    {(projectOptionsQuery.isLoading || (selectedProject && itemsQuery.isLoading)) && <div className="loading-block"><LoadingIndicator label="Cargando información…" /></div>}
    {selectedProject && <section className="card">
          <div className="section-title"><div className="selected-project-title"><h2>{selectedProject.name}</h2><Badge variant="secondary">OBRA {selectedProject.id}</Badge></div><span>Recepción: {formatDate(selectedProject.municipal_reception_date)}</span></div>
          <div className="project-items-list"><DataTable data={items} columns={itemColumns} sorting={[{ id: itemSortBy, desc: itemSortDirection === "desc" }]} onSortingChange={(updater) => { const current = [{ id: itemSortBy, desc: itemSortDirection === "desc" }]; const next = typeof updater === "function" ? updater(current) : updater; const first = next[0]; updateUrlParams({ item_sort: "notes", item_dir: first?.desc ? "desc" : "asc", item_offset: 0 }); }} globalFilter={itemSearch} onGlobalFilterChange={(updater) => updateUrlParams({ item_q: typeof updater === "function" ? updater(itemSearch) : updater, item_offset: 0 })} globalFilterLabel="Buscar observación" globalFilterPlaceholder="Ej. humedad, cielo, ventana" getRowId={(item) => item.public_id} emptyMessage="No hay ítems asociados a esta obra." /></div>
          <div className="pagination project-items-pagination"><Button variant="outline" size="icon" aria-label="Página anterior de ítems" disabled={!itemOffset || itemsQuery.isFetching} onClick={() => updateUrlParams({ item_offset: Math.max(0, itemOffset - ITEM_PAGE_SIZE) })}><ChevronLeft aria-hidden="true" /></Button><span>{totalItems ? `${itemOffset + 1}–${Math.min(itemOffset + ITEM_PAGE_SIZE, totalItems)} de ${totalItems}` : "0 ítems"}</span><Button variant="outline" size="icon" aria-label="Página siguiente de ítems" disabled={itemOffset + ITEM_PAGE_SIZE >= totalItems || itemsQuery.isFetching} onClick={() => updateUrlParams({ item_offset: itemOffset + ITEM_PAGE_SIZE })}><ChevronRight aria-hidden="true" /></Button></div>
    </section>}
  </>;
}
