import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createPaginatedRowModel, flexRender, tableFeatures, type ColumnDef, type PaginationState, type StockFeatures, stockFeatures, useTable } from "@tanstack/react-table";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { associateDocument, createFailureCause, getDocumentPdf, removePostventaItemDocument } from "../../api";
import { postventaItemQueryKeys } from "../../queries/postventa-items";
import { DocumentStatusBadge, ErrorMessage, LoadingIndicator } from "./components";
import { documentQueryKeys, useDocument, useDocumentCandidates, useFailureCauseCategories, useFailureCauses, useUnassociatedItems } from "./queries";
import type { DocumentAssociation, DocumentCandidate, DocumentStatus } from "../../types";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "../../components/ui/card";
import { Checkbox } from "../../components/ui/checkbox";

const suggestedCode = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "");
const candidateTableFeatures = tableFeatures({ ...stockFeatures, paginatedRowModel: createPaginatedRowModel() });

export function ReviewPage() {
  const { publicId } = useParams();
  const [searchParams] = useSearchParams();
  const requestedReturnTo = searchParams.get("returnTo");
  const returnTo = requestedReturnTo && requestedReturnTo.startsWith("/") && !requestedReturnTo.startsWith("//") ? requestedReturnTo : "/documents";
  const queryClient = useQueryClient();
  const documentQuery = useDocument(publicId);
  const document = documentQuery.data;
  const canReview = document?.status === "PENDING_REVIEW" || document?.status === "UNMATCHED" || document?.status === "MATCHED";
  const candidatesQuery = useDocumentCandidates(publicId, canReview);
  const causesQuery = useFailureCauses();
  const categoriesQuery = useFailureCauseCategories();
  const [selected, setSelected] = useState<string[]>([]);
  const [causeCodes, setCauseCodes] = useState<string[]>([]);
  const [isAddingCause, setIsAddingCause] = useState(false);
  const [newCauseName, setNewCauseName] = useState("");
  const [newCauseCode, setNewCauseCode] = useState("");
  const [newCauseCategory, setNewCauseCategory] = useState("");
  const [newCauseAliases, setNewCauseAliases] = useState("");
  const [itemSearch, setItemSearch] = useState("");
  const [candidatePagination, setCandidatePagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 15 });
  const [isOpeningPdf, setIsOpeningPdf] = useState(false);
  const searchedItemsQuery = useUnassociatedItems(itemSearch);
  const candidates = useMemo<DocumentCandidate[]>(() => {
    const suggested = candidatesQuery.data?.items ?? [];
    const searched = itemSearch.trim().length >= 2
      ? (searchedItemsQuery.data?.items ?? []).map((item) => ({ postventa_item_public_id: item.public_id, postventa_item_id: item.id, project_id: item.project_id, project_name: item.project_name, notes: item.notes, score: 0 }))
      : [];
    return [...suggested, ...searched.filter((item) => !suggested.some((candidate) => candidate.postventa_item_public_id === item.postventa_item_public_id))];
  }, [candidatesQuery.data, itemSearch, searchedItemsQuery.data]);
  useEffect(() => {
    setCandidatePagination((current) => ({
      ...current,
      pageIndex: Math.min(current.pageIndex, Math.max(0, Math.ceil(candidates.length / current.pageSize) - 1)),
    }));
  }, [candidates.length]);
  const defaultCauses = useMemo(() => causesQuery.data?.filter((cause) => document?.extracted_failure_cause?.toLocaleLowerCase("es-CL").includes(cause.display_name_es.toLocaleLowerCase("es-CL"))).map((cause) => cause.code) ?? [], [causesQuery.data, document?.extracted_failure_cause]);
  const mutation = useMutation({ mutationFn: () => associateDocument(publicId!, selected, causeCodes.length ? causeCodes : defaultCauses), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: documentQueryKeys.all }); setSelected([]); } });
  const removeAssociationMutation = useMutation({
    mutationFn: (association: DocumentAssociation) => removePostventaItemDocument(association.postventa_item_public_id, publicId!),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: documentQueryKeys.all }),
        queryClient.invalidateQueries({ queryKey: postventaItemQueryKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
  });
  const createCauseMutation = useMutation({
    mutationFn: () => createFailureCause({
      code: newCauseCode,
      displayNameEs: newCauseName,
      categoryCode: newCauseCategory,
      aliases: newCauseAliases.split(",").map((alias) => alias.trim()).filter(Boolean),
    }),
    onSuccess: async (cause) => {
      setCauseCodes((current) => current.includes(cause.code) ? current : [...current, cause.code]);
      setNewCauseName(""); setNewCauseCode(""); setNewCauseCategory(""); setNewCauseAliases(""); setIsAddingCause(false);
      await queryClient.invalidateQueries({ queryKey: documentQueryKeys.failureCauses() });
    },
  });
  const toggleItem = (id: string, checked: boolean) => setSelected((current) => checked ? [...current, id] : current.filter((selectedId) => selectedId !== id));
  const candidateColumns = useMemo<ColumnDef<StockFeatures, DocumentCandidate, unknown>[]>(() => [
    {
      id: "selection",
      header: "",
      enableSorting: false,
      cell: ({ row }) => <Checkbox aria-label={`Seleccionar ítem ${row.original.postventa_item_id}`} checked={selected.includes(row.original.postventa_item_public_id)} onCheckedChange={(checked) => toggleItem(row.original.postventa_item_public_id, checked === true)} />,
    },
    { accessorKey: "project_id", header: "Obra", enableSorting: false, cell: ({ row }) => `${row.original.project_id} · ${row.original.project_name}` },
    { accessorKey: "notes", header: "Observación", enableSorting: false },
    { id: "score", header: "Similitud", enableSorting: false, cell: ({ row }) => row.original.score ? `${Math.round(row.original.score * 100)}%` : "Manual" },
  ], [selected]);
  const candidateTable = useTable({
    features: candidateTableFeatures,
    data: candidates,
    columns: candidateColumns,
    state: { pagination: candidatePagination },
    onPaginationChange: setCandidatePagination,
    getRowId: (candidate) => candidate.postventa_item_public_id,
  });
  const openPdf = async () => { if (!publicId) return; setIsOpeningPdf(true); const preview = window.open("", "_blank"); try { const blob = await getDocumentPdf(publicId); const url = URL.createObjectURL(blob); if (preview) preview.location.href = url; window.setTimeout(() => URL.revokeObjectURL(url), 60_000); } catch { preview?.close(); } finally { setIsOpeningPdf(false); } };
  if (documentQuery.isLoading) return <div className="loading-block"><LoadingIndicator label="Cargando documento…" /></div>;
  if (!document) return <><ErrorMessage error={documentQuery.error} /><Link to={returnTo}>Volver al historial</Link></>;
  const chosenCauses = causeCodes.length ? causeCodes : defaultCauses;
  return <section className="review-layout">
    <Card className="gap-0 overflow-hidden py-0"><CardHeader className="py-5"><div><p className="eyebrow">DOCUMENTO</p><CardTitle>{document.original_filename}</CardTitle></div><DocumentStatusBadge status={document.status as DocumentStatus} /></CardHeader><CardContent className="px-0"><div className="detail-grid"><div><strong>Cargado</strong><p>{new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short" }).format(new Date(document.uploaded_at))}</p></div><div><strong>Proyecto detectado</strong><p>{document.extracted_data?.project_number?.match(/^\s*(\d+)/)?.[1] || "No detectado"} {document.extracted_data?.project_name || ""}</p></div><div><strong>Lugar</strong><p>{document.extracted_data?.infiltration_location || "No detectado"}</p></div><div className="detail-grid-full"><strong>Causa extraída</strong><p>{document.extracted_failure_cause || "No detectada"}</p></div></div></CardContent><CardFooter className="card-actions"><Button disabled={isOpeningPdf} onClick={() => void openPdf()}>{isOpeningPdf ? <LoadingIndicator label="Abriendo PDF…" compact /> : "Abrir PDF"}</Button></CardFooter>{document.processing_error && <ErrorMessage error={new Error(document.processing_error)} />}</Card>
    <Card className="gap-0 overflow-hidden py-0"><CardHeader className="py-5"><CardTitle>Asociaciones</CardTitle><CardAction>{document.associations.length}</CardAction></CardHeader><CardContent className="px-0"><ErrorMessage error={removeAssociationMutation.error} />{document.associations.length ? <ul className="association-list">{document.associations.map((association) => <li key={association.postventa_item_public_id}><strong>{association.project_id} · Ítem {association.postventa_item_id}</strong><span>{association.notes}</span><div>{association.failure_causes.length ? association.failure_causes.map((cause) => <span className="mr-1 mb-1 inline-block" key={cause.code}><Badge variant="secondary">{cause.display_name_es}</Badge></span>) : <small>Sin causa asociada</small>}</div><small>{association.association_source === "MANUAL" ? "Manual" : "Automática"}</small><Button variant="ghost" size="icon" className="icon-danger-action" aria-label={`Desasociar ítem ${association.postventa_item_id}`} title="Desasociar ítem" disabled={removeAssociationMutation.isPending} onClick={() => { if (window.confirm("¿Desasociar este ítem del documento? El PDF no se eliminará.")) removeAssociationMutation.mutate(association); }}>{removeAssociationMutation.isPending && removeAssociationMutation.variables?.postventa_item_public_id === association.postventa_item_public_id ? <LoadingIndicator label="Desasociando…" compact /> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="m10 14 4-4" /><path d="m8.5 8.5-1-1a3 3 0 0 0-4.25 4.25l2.5 2.5A3 3 0 0 0 10 14.5l1-1" /><path d="m15.5 15.5 1 1a3 3 0 0 0 4.25-4.25l-2.5-2.5A3 3 0 0 0 14 9.5l-1 1" /></svg>}</Button></li>)}</ul> : <p className="empty-state">Aún no existen asociaciones.</p>}</CardContent></Card>
    {canReview && <Card className="gap-0 overflow-hidden py-0"><CardHeader className="py-5"><div><p className="eyebrow">REVISIÓN MANUAL</p><CardTitle>Seleccionar ítems y causas</CardTitle></div><CardAction>{candidates.length} candidatos</CardAction></CardHeader><CardContent className="px-0"><ErrorMessage error={candidatesQuery.error ?? causesQuery.error ?? categoriesQuery.error ?? searchedItemsQuery.error ?? mutation.error ?? createCauseMutation.error} /><div className="review-form"><label>Causas normalizadas<Select value={causeCodes[0] ?? "__none__"} onValueChange={(value) => { if (value === "__none__") return; setCauseCodes((current) => current.includes(value) ? current.filter((code) => code !== value) : [...current, value]); }}><SelectTrigger><SelectValue placeholder="Selecciona causas" /></SelectTrigger><SelectContent><SelectItem value="__none__">Selecciona una causa</SelectItem>{causesQuery.data?.map((cause) => <SelectItem key={cause.code} value={cause.code}>{cause.category_name_es} · {cause.display_name_es}</SelectItem>)}</SelectContent></Select></label><p className="muted">Selecciona una causa a la vez; vuelve a abrir el menú para agregar o quitar otras.</p><Button variant="secondary" onClick={() => { setIsAddingCause((current) => !current); if (!isAddingCause) setNewCauseAliases(document.extracted_failure_cause ?? ""); }}>{isAddingCause ? "Cancelar nueva causa" : "Agregar nueva causa"}</Button>{isAddingCause && <fieldset className="new-cause-form"><legend>Nueva causa normalizada</legend><label>Nombre visible en español<input value={newCauseName} onChange={(event) => { setNewCauseName(event.target.value); setNewCauseCode(suggestedCode(event.target.value)); }} placeholder="Ej. Sellos desprendidos" /></label><label>Código para BI<input value={newCauseCode} onChange={(event) => setNewCauseCode(suggestedCode(event.target.value))} placeholder="SELLOS_DESPRENDIDOS" /></label><label>Categoría<Select value={newCauseCategory || "__none__"} onValueChange={(value) => setNewCauseCategory(value === "__none__" ? "" : value)}><SelectTrigger><SelectValue placeholder="Selecciona una categoría" /></SelectTrigger><SelectContent><SelectItem value="__none__">Selecciona una categoría</SelectItem>{categoriesQuery.data?.map((category) => <SelectItem key={category.code} value={category.code}>{category.display_name_es}</SelectItem>)}</SelectContent></Select></label><label>Alias de detección (separados por coma)<input value={newCauseAliases} onChange={(event) => setNewCauseAliases(event.target.value)} placeholder="sellos desprendidos, sello suelto" /></label><Button disabled={!newCauseName || !newCauseCode || !newCauseCategory || createCauseMutation.isPending} onClick={() => createCauseMutation.mutate()}>{createCauseMutation.isPending ? <LoadingIndicator label="Creando causa…" compact /> : "Crear y seleccionar causa"}</Button></fieldset>}<label>Buscar otro ítem libre<input value={itemSearch} onChange={(event) => { setItemSearch(event.target.value); setCandidatePagination((current) => ({ ...current, pageIndex: 0 })); }} placeholder="Obra, proyecto u observación" /></label>{(candidatesQuery.isFetching || searchedItemsQuery.isFetching) && <LoadingIndicator label="Buscando ítems…" compact />}<div className="table-wrap"><table><thead>{candidateTable.getHeaderGroups().map((headerGroup) => <tr key={headerGroup.id}>{headerGroup.headers.map((header) => <th key={header.id}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{candidateTable.getRowModel().rows.map((row) => <tr key={row.id}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}{!candidateTable.getRowModel().rows.length && <tr><td colSpan={candidateColumns.length}>No hubo candidatos. Busca un ítem libre para asociarlo manualmente.</td></tr>}</tbody></table></div>{candidates.length > 0 && <div className="pagination"><label>Filas por página<Select value={String(candidatePagination.pageSize)} onValueChange={(value) => setCandidatePagination({ pageIndex: 0, pageSize: Number(value) })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="15">15</SelectItem><SelectItem value="25">25</SelectItem><SelectItem value="50">50</SelectItem></SelectContent></Select></label><Button variant="secondary" size="sm" disabled={!candidateTable.getCanPreviousPage()} onClick={() => candidateTable.previousPage()}>Anterior</Button><span>{`${candidatePagination.pageIndex * candidatePagination.pageSize + 1}–${Math.min((candidatePagination.pageIndex + 1) * candidatePagination.pageSize, candidates.length)} de ${candidates.length}`}</span><Button variant="secondary" size="sm" disabled={!candidateTable.getCanNextPage()} onClick={() => candidateTable.nextPage()}>Siguiente</Button></div>}<Button disabled={!selected.length || !chosenCauses.length || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <LoadingIndicator label="Guardando asociación…" compact /> : "Confirmar asociación manual"}</Button></div></CardContent></Card>}
    <Link to={returnTo}>Volver al historial</Link>
  </section>;
}
