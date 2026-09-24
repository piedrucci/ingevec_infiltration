import { useCallback, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef, SortingState, StockFeatures } from "@tanstack/react-table";

import { deleteDocument } from "../../api";
import type { Document, DocumentStatus } from "../../types";
import { DocumentResultIndicator, DocumentStatusBadge, ErrorMessage, LoadingIndicator } from "./components";
import { documentQueryKeys, useDocuments } from "./queries";
import { DataTable } from "../../components/DataTable";
import { useUrlSearchParams } from "../evaluation/useEvaluationSearchParams";

const statuses: Array<[string, string]> = [["", "Todos"], ["QUEUED", "En cola"], ["PROCESSING", "Procesando"], ["MATCHED", "Asociados"], ["PENDING_REVIEW", "Revisión"], ["UNMATCHED", "Sin asociación"], ["FAILED", "Con error"]];
const pageSizes = [15, 25, 50] as const;
const sortableColumns = ["document_name", "obra", "status"] as const;
const dateTime = (value: string) => new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));

export function DocumentsPage() {
  const location = useLocation();
  const { searchParams, updateUrlParams } = useUrlSearchParams();
  const requestedPageSize = Number(searchParams.get("limit") ?? "15");
  const pageSize = pageSizes.includes(requestedPageSize as (typeof pageSizes)[number]) ? requestedPageSize : 15;
  const requestedOffset = Number(searchParams.get("offset") ?? "0");
  const offset = Number.isSafeInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0;
  const status = statuses.some(([value]) => value === (searchParams.get("status") ?? "")) ? (searchParams.get("status") ?? "") : "";
  const search = searchParams.get("q") ?? "";
  const requestedSortBy = searchParams.get("sort") ?? "";
  const sortBy = sortableColumns.find((column) => column === requestedSortBy);
  const sortDirection = searchParams.get("dir") === "desc" ? "desc" : "asc";
  const sorting: SortingState = sortBy ? [{ id: sortBy, desc: sortDirection === "desc" }] : [];
  const [deletingDocument, setDeletingDocument] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<Error | null>(null);
  const queryClient = useQueryClient();
  const documentsQuery = useDocuments(status, search, pageSize, offset, sortBy ?? "project_id", sortDirection);
  const documents = documentsQuery.data?.items ?? [];
  const total = documentsQuery.data?.page.total ?? 0;
  const hasPrevious = offset > 0;
  const hasNext = offset + pageSize < total;

  const changeStatus = (value: string) => {
    updateUrlParams({ status: value, offset: null });
  };

  const changePageSize = (value: number) => {
    updateUrlParams({ limit: value, offset: null });
  };

  const changeSearch = (value: string) => {
    updateUrlParams({ q: value, offset: null });
  };

  const removeDocument = useCallback(async (publicId: string, filename: string) => {
    if (!window.confirm(`¿Eliminar el documento "${filename}"? Esta acción no se puede deshacer.`)) return;
    setDeleteError(null);
    setDeletingDocument(publicId);
    try {
      await deleteDocument(publicId);
      await queryClient.invalidateQueries({ queryKey: documentQueryKeys.all });
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason : new Error("No fue posible eliminar el documento."));
    } finally {
      setDeletingDocument(null);
    }
  }, [queryClient]);

  const documentColumns = useMemo<ColumnDef<StockFeatures, Document, unknown>[]>(() => [
    {
      id: "document_name",
      header: "Archivo",
      accessorFn: (document) => document.original_filename,
      cell: ({ row }) => <Link to={`/documents/${row.original.public_id}/review?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`}>{row.original.original_filename}</Link>,
    },
    {
      id: "obra",
      header: "Obra",
      accessorFn: (document) => document.projects?.[0] ?? document.extracted_data?.project_number ?? "",
      cell: ({ row }) => {
        const projects = row.original.projects ?? [];
        const detectedProject = row.original.extracted_data?.project_number;
        return projects.length ? projects.join(", ") : (detectedProject?.match(/^\s*(\d+)/)?.[1] || "-");
      },
    },
    {
      id: "status",
      header: "Estado",
      accessorFn: (document) => document.status,
      cell: ({ row }) => <DocumentStatusBadge status={row.original.status as DocumentStatus} />,
    },
    { accessorKey: "association_count", header: "Asociaciones", enableSorting: false },
    { accessorKey: "uploaded_at", header: "Fecha de carga", enableSorting: false, cell: ({ getValue }) => dateTime(getValue<string>()) },
    {
      id: "result",
      header: "Resultado",
      enableSorting: false,
      cell: ({ row }) => {
        const result = row.original.processing_error || (row.original.status === "MATCHED" ? "Procesado correctamente" : null);
        return result ? <DocumentResultIndicator message={result} error={Boolean(row.original.processing_error)} /> : "-";
      },
    },
    {
      id: "actions",
      header: "Acciones",
      enableSorting: false,
      cell: ({ row }) => <button className="danger document-delete-button" type="button" aria-label={`Eliminar documento ${row.original.original_filename}`} title={`Eliminar ${row.original.original_filename}`} disabled={deletingDocument === row.original.public_id} onClick={() => void removeDocument(row.original.public_id, row.original.original_filename)}>{deletingDocument === row.original.public_id ? <LoadingIndicator label="Eliminando…" compact /> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3" /></svg>}</button>,
    },
  ], [deletingDocument, location.pathname, location.search, removeDocument]);

  return <section className="card">
    <div className="section-title"><div><p className="eyebrow">DOCUMENTOS</p><h2>Historial de cargas</h2></div><Link className="button-link" to="/documents/upload">Cargar PDFs</Link></div>
    <div className="filters">
      <label>Buscar <input type="search" value={search} placeholder="Archivo o número de obra" onChange={(event) => changeSearch(event.target.value)} /></label>
      <label>Estado <select value={status} onChange={(event) => changeStatus(event.target.value)}>{statuses.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>Filas por página <select value={pageSize} onChange={(event) => changePageSize(Number(event.target.value))}>{pageSizes.map((size) => <option value={size} key={size}>{size}</option>)}</select></label>
      <span>{total} documentos</span>
    </div>
    <ErrorMessage error={deleteError ?? documentsQuery.error} />
    {documentsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando documentos…" /></div>}
    <DataTable data={documents} columns={documentColumns} sorting={sorting} onSortingChange={(updater) => { const next = typeof updater === "function" ? updater(sorting) : updater; const first = next[0]; updateUrlParams({ sort: first?.id ?? null, dir: first?.desc ? "desc" : "asc", offset: null }); }} getRowId={(document) => document.public_id} emptyMessage="No hay documentos para este filtro." />
    <div className="pagination"><button className="secondary" type="button" disabled={!hasPrevious || documentsQuery.isFetching} onClick={() => updateUrlParams({ offset: Math.max(0, offset - pageSize) })}>Anterior</button><span>{total ? `${offset + 1}–${Math.min(offset + pageSize, total)} de ${total}` : "0 documentos"}</span><button className="secondary" type="button" disabled={!hasNext || documentsQuery.isFetching} onClick={() => updateUrlParams({ offset: offset + pageSize })}>Siguiente</button></div>
  </section>;
}
