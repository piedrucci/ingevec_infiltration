import { useCallback, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef, SortingState, StockFeatures } from "@tanstack/react-table";

import { deleteDocument } from "../../api";
import type { Document, DocumentStatus } from "../../types";
import { DocumentResultIndicator, DocumentStatusBadge, ErrorMessage, LoadingIndicator } from "./components";
import { documentQueryKeys, useDocuments } from "./queries";
import { DataTable } from "../../components/DataTable";
import { Button, buttonVariants } from "../../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Input } from "../../components/ui/input";
import { Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "../../components/ui/card";
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
      cell: ({ row }) => <div className="flex flex-col gap-1"><Link to={`/documents/${row.original.public_id}/review?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`}>{row.original.original_filename}</Link><span className="text-xs text-muted-foreground">{dateTime(row.original.uploaded_at)}</span></div>,
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
      cell: ({ row }) => <Button variant="destructive" size="icon" className="document-delete-button" aria-label={`Eliminar documento ${row.original.original_filename}`} title={`Eliminar ${row.original.original_filename}`} disabled={deletingDocument === row.original.public_id} onClick={() => void removeDocument(row.original.public_id, row.original.original_filename)}>{deletingDocument === row.original.public_id ? <LoadingIndicator label="Eliminando…" compact /> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3" /></svg>}</Button>,
    },
  ], [deletingDocument, location.pathname, location.search, removeDocument]);

  return <Card className="gap-0 overflow-hidden py-0">
    <CardHeader className="py-5"><div><p className="eyebrow">DOCUMENTOS</p><CardTitle>Historial de cargas</CardTitle></div><CardAction><Link className={buttonVariants()} to="/documents/upload">Cargar PDFs</Link></CardAction></CardHeader>
    <CardContent className="px-0">
      <div className="filters">
        <label>Buscar <Input type="search" value={search} placeholder="Archivo o número de obra" onChange={(event) => changeSearch(event.target.value)} /></label>
        <label>Estado <Select value={status || "ALL"} onValueChange={(value) => changeStatus(value === "ALL" ? "" : value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{statuses.map(([value, label]) => <SelectItem value={value || "ALL"} key={value}>{label}</SelectItem>)}</SelectContent></Select></label>
        <label>Filas por página <Select value={String(pageSize)} onValueChange={(value) => changePageSize(Number(value))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{pageSizes.map((size) => <SelectItem value={String(size)} key={size}>{size}</SelectItem>)}</SelectContent></Select></label>
        <span>{total} documentos</span>
      </div>
      <ErrorMessage error={deleteError ?? documentsQuery.error} />
      {documentsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando documentos…" /></div>}
      <DataTable data={documents} columns={documentColumns} sorting={sorting} onSortingChange={(updater) => { const next = typeof updater === "function" ? updater(sorting) : updater; const first = next[0]; updateUrlParams({ sort: first?.id ?? null, dir: first?.desc ? "desc" : "asc", offset: null }); }} getRowId={(document) => document.public_id} emptyMessage="No hay documentos para este filtro." />
    </CardContent>
    <CardFooter className="pagination"><Button variant="secondary" size="sm" disabled={!hasPrevious || documentsQuery.isFetching} onClick={() => updateUrlParams({ offset: Math.max(0, offset - pageSize) })}>Anterior</Button><span>{total ? `${offset + 1}–${Math.min(offset + pageSize, total)} de ${total}` : "0 documentos"}</span><Button variant="secondary" size="sm" disabled={!hasNext || documentsQuery.isFetching} onClick={() => updateUrlParams({ offset: offset + pageSize })}>Siguiente</Button></CardFooter>
  </Card>;
}
