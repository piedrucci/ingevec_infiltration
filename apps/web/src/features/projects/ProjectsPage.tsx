import { type FormEvent, useCallback, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { ColumnDef, SortingState, StockFeatures } from "@tanstack/react-table";

import { getDocumentPdf } from "../../api";
import { usePostventaItems } from "../../queries/postventa-items";
import { useProjects } from "../../queries/projects";
import type { PostventaItem, Project } from "../../types";
import { ErrorMessage, LoadingIndicator, ReconciliationBadge } from "../documents/components";
import { useUrlSearchParams } from "../evaluation/useEvaluationSearchParams";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Input } from "../../components/ui/input";

const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat("es-CL").format(new Date(`${value}T00:00:00`)) : "-";
const PAGE_SIZE = 50;
const sortableProjectColumns = new Set(["id", "name", "typology", "location", "supervisor", "project_manager", "project_admin"]);

export function ProjectsPage() {
  const location = useLocation();
  const { searchParams, updateUrlParams } = useUrlSearchParams();
  const search = searchParams.get("q") ?? "";
  const selectedProjectId = searchParams.get("project");
  const itemSearch = searchParams.get("item_q") ?? "";
  const requestedOffset = Number(searchParams.get("offset") ?? "0");
  const offset = Number.isSafeInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0;
  const requestedSort = searchParams.get("sort") ?? "id";
  const sortBy = sortableProjectColumns.has(requestedSort) ? requestedSort : "id";
  const sortDirection = searchParams.get("dir") === "desc" ? "desc" : "asc";
  const [documentError, setDocumentError] = useState<Error | null>(null);
  const [openingDocument, setOpeningDocument] = useState<string | null>(null);
  const projectsQuery = useProjects({ search, limit: PAGE_SIZE, offset, sortBy, sortDirection });
  const projects = projectsQuery.data?.items ?? [];
  const totalProjects = projectsQuery.data?.page.total ?? 0;
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const itemsQuery = usePostventaItems(selectedProject?.id ?? null, itemSearch);
  const items = itemsQuery.data?.items ?? [];

  const openDocument = useCallback(async (documentPublicId: string) => {
    setDocumentError(null);
    setOpeningDocument(documentPublicId);
    const preview = window.open("", "_blank");
    try {
      const pdf = await getDocumentPdf(documentPublicId);
      const objectUrl = URL.createObjectURL(pdf);
      if (preview) preview.location.href = objectUrl;
      else window.open(objectUrl, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (reason) {
      preview?.close();
      setDocumentError(reason instanceof Error ? reason : new Error("No fue posible abrir el documento."));
    } finally {
      setOpeningDocument(null);
    }
  }, []);

  const submitSearch = (event: FormEvent) => { event.preventDefault(); };
  const sorting: SortingState = [{ id: sortBy, desc: sortDirection === "desc" }];
  const projectColumns = useMemo<ColumnDef<StockFeatures, Project, unknown>[]>(() => [
    { accessorKey: "id", header: "Obra" },
    { accessorKey: "name", header: "Proyecto" },
    { accessorKey: "typology", header: "Tipología" },
    { accessorKey: "location", header: "Ubicación" },
    { accessorKey: "supervisor", header: "Supervisor" },
    { accessorKey: "project_admin", header: "Administrador de proyecto", cell: ({ getValue }) => getValue<string>() || "-" },
  ], []);
  const itemColumns = useMemo<ColumnDef<StockFeatures, PostventaItem, unknown>[]>(() => [
    { accessorKey: "id", header: "Ítem", enableSorting: false },
    { accessorKey: "notes", header: "Observación", enableSorting: false },
    { accessorKey: "classification", header: "Clasificación", enableSorting: false },
    { accessorKey: "item_type", header: "Tipo", enableSorting: false },
    {
      id: "causes",
      header: "Causas",
      enableSorting: false,
      cell: ({ row }) => row.original.failure_causes.length
        ? row.original.failure_causes.map((cause) => <span className="mr-1 mb-1 inline-block" key={cause.code}><Badge variant="secondary">{cause.display_name_es}</Badge></span>)
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
      id: "document",
      header: "Documento",
      enableSorting: false,
      cell: ({ row }) => {
        const document = row.original.document;
        if (!document) return "Sin documento";
        return <Button variant="ghost" size="icon" className="document-link document-icon-link" aria-label={`Abrir documento ${document.original_filename}`} title={`${document.original_filename} · ${document.status}`} disabled={openingDocument === document.public_id} onClick={() => void openDocument(document.public_id)}>{openingDocument === document.public_id ? <LoadingIndicator label="Abriendo…" compact /> : <svg aria-hidden="true" viewBox="0 0 32 36" focusable="false"><path d="M4 1h16l8 8v26H4z" /><path d="M20 1v9h8" /><text x="7" y="26">PDF</text></svg>}</Button>;
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
  ], [location.pathname, location.search, openingDocument, openDocument]);
  return <>
    <section className="toolbar"><form onSubmit={submitSearch}><label htmlFor="search">Buscar proyecto</label><Input id="search" value={search} onChange={(event) => updateUrlParams({ q: event.target.value, project: null })} placeholder="Ej. 712 o PAM" /><Button type="submit">Buscar</Button></form></section>
    <ErrorMessage error={documentError ?? projectsQuery.error ?? itemsQuery.error} />
    {(projectsQuery.isLoading || itemsQuery.isLoading) && <div className="loading-block"><LoadingIndicator label="Cargando información…" /></div>}
    <section className="card"><div className="section-title"><h2>Proyectos</h2><span>{totalProjects.toLocaleString("es-CL")} proyectos</span></div><DataTable data={projects} columns={projectColumns} sorting={sorting} onSortingChange={(updater) => { const next = typeof updater === "function" ? updater(sorting) : updater; const first = next[0]; updateUrlParams({ sort: first?.id ?? "id", dir: first?.desc ? "desc" : "asc", offset: null }); }} getRowId={(project) => project.id} selectedRowId={selectedProject?.id ?? null} onRowClick={(row) => updateUrlParams({ project: row.original.id })} emptyMessage="No hay proyectos para la búsqueda seleccionada." /><div className="pagination"><Button variant="secondary" size="sm" disabled={!offset || projectsQuery.isFetching} onClick={() => updateUrlParams({ offset: Math.max(0, offset - PAGE_SIZE) })}>Anterior</Button><span>{totalProjects ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, totalProjects)} de ${totalProjects}` : "0 proyectos"}</span><Button variant="secondary" size="sm" disabled={offset + PAGE_SIZE >= totalProjects || projectsQuery.isFetching} onClick={() => updateUrlParams({ offset: offset + PAGE_SIZE })}>Siguiente</Button></div></section>
    {selectedProject && <section className="card"><div className="section-title"><div><p className="eyebrow">OBRA {selectedProject.id}</p><h2>{selectedProject.name}</h2></div><span>Recepción: {formatDate(selectedProject.municipal_reception_date)}</span></div><DataTable data={items} columns={itemColumns} globalFilter={itemSearch} onGlobalFilterChange={(updater) => updateUrlParams({ item_q: typeof updater === "function" ? updater(itemSearch) : updater })} globalFilterLabel="Buscar observación" globalFilterPlaceholder="Ej. humedad, cielo, ventana" getRowId={(item) => item.public_id} emptyMessage="No hay ítems asociados a esta obra." /></section>}
  </>;
}
