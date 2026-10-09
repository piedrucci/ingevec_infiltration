import { useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ColumnDef, SortingState, StockFeatures } from "@tanstack/react-table";

import { getDocumentPdf } from "../../api";
import { useDashboardSummary } from "../../queries/dashboard";
import { usePostventaItemsByProjectManager } from "../../queries/postventa-items";
import { ErrorMessage, LoadingIndicator, ReconciliationBadge } from "../documents/components";
import { Button } from "../../components/ui/button";
import { IconActionLink } from "../../components/IconActionLink";
import { Badge } from "../../components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Input } from "../../components/ui/input";
import { DataTable } from "../../components/DataTable";
import type { PostventaItem } from "../../types";

const PAGE_SIZE = 50;

export function ProjectManagerItemsPage() {
  const { projectManagerId: rawProjectManagerId } = useParams();
  const location = useLocation();
  const projectManagerId = rawProjectManagerId && /^\d+$/.test(rawProjectManagerId) ? Number(rawProjectManagerId) : null;
  const [search, setSearch] = useState("");
  const [documentStatus, setDocumentStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [sorting, setSorting] = useState<SortingState>([{ id: "project_id", desc: false }]);
  const [openingDocument, setOpeningDocument] = useState<string | null>(null);
  const [documentError, setDocumentError] = useState<Error | null>(null);
  const summaryQuery = useDashboardSummary();
  const sortBy = sorting[0]?.id === "notes" ? "notes" : "project_id";
  const sortDirection = sorting[0]?.desc ? "desc" : "asc";
  const itemsQuery = usePostventaItemsByProjectManager(projectManagerId, { search, documentStatus, offset, sortBy, sortDirection });
  const manager = summaryQuery.data?.project_manager_association_progress.find((row) => row.project_manager_id === projectManagerId);
  const items = itemsQuery.data?.items ?? [];
  const total = itemsQuery.data?.page.total ?? 0;
  const hasPrevious = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;
  const itemColumns = useMemo<ColumnDef<StockFeatures, PostventaItem, unknown>[]>(() => [
    { accessorKey: "project_id", header: "Obra", cell: ({ row }) => <>{row.original.project_id} · {row.original.project_name}</> },
    { accessorKey: "notes", header: "Observación" },
    { accessorKey: "classification", header: "Clasificación", enableSorting: false },
    { id: "causes", header: "Causas", enableSorting: false, cell: ({ row }) => row.original.failure_causes.length ? row.original.failure_causes.map((cause) => <span className="mr-1 mb-1 inline-block" key={cause.code}><Badge variant="secondary">{cause.display_name_es}</Badge></span>) : "Sin causa" },
    { id: "status", header: "Estado", enableSorting: false, cell: ({ row }) => <ReconciliationBadge reconciled={row.original.reconciliation_status === "RECONCILED"} /> },
    { id: "document", header: "Documento", enableSorting: false, cell: ({ row }) => {
      const document = row.original.document;
      return document ? <Button variant="ghost" size="icon" className="text-primary hover:bg-accent hover:text-accent-foreground [&_svg]:h-8 [&_svg]:w-[1.8rem] [&_svg_path]:fill-none [&_svg_path]:stroke-current [&_svg_path]:[stroke-linejoin:round] [&_svg_path]:[stroke-width:1.6] [&_svg_text]:fill-current [&_svg_text]:text-[7px] [&_svg_text]:font-bold" aria-label={`Abrir documento ${document.original_filename}`} title={`${document.original_filename} · ${document.status}`} disabled={openingDocument === document.public_id} onClick={() => void openDocument(document.public_id)}>{openingDocument === document.public_id ? <LoadingIndicator label="Abriendo…" compact /> : <svg aria-hidden="true" viewBox="0 0 32 36" focusable="false"><path d="M4 1h16l8 8v26H4z" /><path d="M20 1v9h8" /><text x="7" y="26">PDF</text></svg>}</Button> : "Sin documento";
    } },
    { id: "action", header: "", enableSorting: false, cell: ({ row }) => <IconActionLink aria-label={row.original.reconciliation_status === "RECONCILED" ? "Editar causas" : "Evaluar ítem"} title={row.original.reconciliation_status === "RECONCILED" ? "Editar causas" : "Evaluar ítem"} to={`/items/${row.original.public_id}/evaluation?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`}>{row.original.reconciliation_status === "RECONCILED" ? <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M4 16.5V20h3.5L18 9.5 14.5 6 4 16.5Z" /><path d="m13.5 7 3.5 3.5" /></svg> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M9 5h6" /><path d="M9 3h6v4H9z" /><path d="M6 5H4v16h16V5h-2" /><path d="m8 13 2 2 5-5" /></svg>}</IconActionLink> },
  ], [location.pathname, location.search, openingDocument]);

  const openDocument = async (documentPublicId: string) => {
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
  };

  if (projectManagerId === null) return <ErrorMessage error={new Error("El gerente de proyecto indicado no es válido.")} />;

  return <>
    <section className="dashboard-heading"><div><Link className="back-link" to="/">← Volver al resumen</Link><div className="mt-2 flex flex-wrap items-center gap-3"><h2>{manager?.name ?? `Gerente #${projectManagerId}`}</h2><Badge variant="secondary">GERENTE DE PROYECTO</Badge></div><p className="muted mt-1">Ítems asociados a este gerente de proyecto</p></div><span>{total.toLocaleString("es-CL")} ítems</span></section>
    <section className="mb-5 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm">
      <div className="filters"><label htmlFor="manager-search">Buscar <Input id="manager-search" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} placeholder="Obra o descripción" /></label><label>Documento <Select value={documentStatus || "ALL"} onValueChange={(value) => { setDocumentStatus(value === "ALL" ? "" : value); setOffset(0); }}><SelectTrigger id="manager-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="ALL">Todos</SelectItem><SelectItem value="MATCHED">Asociados</SelectItem><SelectItem value="PENDING_REVIEW">Requieren revisión</SelectItem><SelectItem value="UNMATCHED">Sin asociación</SelectItem><SelectItem value="FAILED">Con error</SelectItem></SelectContent></Select></label></div>
      <ErrorMessage error={documentError ?? summaryQuery.error ?? itemsQuery.error} />
      {itemsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando ítems…" /></div>}
      <DataTable data={items} columns={itemColumns} sorting={sorting} onSortingChange={(updater) => { const next = typeof updater === "function" ? updater(sorting) : updater; const first = next[0]; const nextSortBy = first?.id === "notes" ? "notes" : "project_id"; setSorting([{ id: nextSortBy, desc: Boolean(first?.desc) }]); setOffset(0); }} getRowId={(item) => item.public_id} emptyMessage="No hay ítems para este gerente con los filtros seleccionados." />
      <div className="flex items-center justify-end gap-3 px-5 py-3"><Button variant="outline" size="icon" aria-label="Página anterior" disabled={!hasPrevious || itemsQuery.isFetching} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}><ChevronLeft aria-hidden="true" /></Button><span className="text-xs text-muted-foreground">{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${total}` : "0 ítems"}</span><Button variant="outline" size="icon" aria-label="Página siguiente" disabled={!hasNext || itemsQuery.isFetching} onClick={() => setOffset((value) => value + PAGE_SIZE)}><ChevronRight aria-hidden="true" /></Button></div>
    </section>
  </>;
}
