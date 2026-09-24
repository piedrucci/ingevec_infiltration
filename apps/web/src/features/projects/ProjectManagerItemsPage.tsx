import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { getDocumentPdf } from "../../api";
import { useDashboardSummary } from "../../queries/dashboard";
import { usePostventaItemsByProjectManager } from "../../queries/postventa-items";
import { ErrorMessage, LoadingIndicator, ReconciliationBadge } from "../documents/components";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Input } from "../../components/ui/input";

const PAGE_SIZE = 50;

export function ProjectManagerItemsPage() {
  const { projectManagerId: rawProjectManagerId } = useParams();
  const location = useLocation();
  const projectManagerId = rawProjectManagerId && /^\d+$/.test(rawProjectManagerId) ? Number(rawProjectManagerId) : null;
  const [search, setSearch] = useState("");
  const [documentStatus, setDocumentStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [openingDocument, setOpeningDocument] = useState<string | null>(null);
  const [documentError, setDocumentError] = useState<Error | null>(null);
  const summaryQuery = useDashboardSummary();
  const itemsQuery = usePostventaItemsByProjectManager(projectManagerId, { search, documentStatus, offset });
  const manager = summaryQuery.data?.project_manager_association_progress.find((row) => row.project_manager_id === projectManagerId);
  const items = itemsQuery.data?.items ?? [];
  const total = itemsQuery.data?.page.total ?? 0;
  const hasPrevious = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

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
    <section className="dashboard-heading"><div><Link className="back-link" to="/">← Volver al resumen</Link><p className="eyebrow">GERENTE DE PROYECTO</p><h2>{manager?.name ?? `Gerente #${projectManagerId}`}</h2><p className="muted">Ítems asociados a este gerente de proyecto</p></div><span>{total.toLocaleString("es-CL")} ítems</span></section>
    <section className="card">
      <div className="filters"><label htmlFor="manager-search">Buscar <Input id="manager-search" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} placeholder="Obra o descripción" /></label><label>Documento <Select value={documentStatus || "ALL"} onValueChange={(value) => { setDocumentStatus(value === "ALL" ? "" : value); setOffset(0); }}><SelectTrigger id="manager-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="ALL">Todos</SelectItem><SelectItem value="MATCHED">Asociados</SelectItem><SelectItem value="PENDING_REVIEW">Requieren revisión</SelectItem><SelectItem value="UNMATCHED">Sin asociación</SelectItem><SelectItem value="FAILED">Con error</SelectItem></SelectContent></Select></label></div>
      <ErrorMessage error={documentError ?? summaryQuery.error ?? itemsQuery.error} />
      {itemsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando ítems…" /></div>}
      <div className="table-wrap"><table><thead><tr><th>Obra</th><th>Observación</th><th>Clasificación</th><th>Tipo</th><th>Causas</th><th>Estado</th><th>Documento</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.public_id}><td>{item.project_id} · {item.project_name}</td><td>{item.notes}</td><td>{item.classification}</td><td>{item.item_type}</td><td>{item.failure_causes.length ? item.failure_causes.map((cause) => <span className="mr-1 mb-1 inline-block" key={cause.code}><Badge variant="secondary">{cause.display_name_es}</Badge></span>) : "Sin causa"}</td><td><ReconciliationBadge reconciled={item.reconciliation_status === "RECONCILED"} /></td><td>{item.document ? <Button variant="ghost" size="icon" className="document-link document-icon-link" aria-label={`Abrir documento ${item.document.original_filename}`} title={`${item.document.original_filename} · ${item.document.status}`} disabled={openingDocument === item.document.public_id} onClick={() => void openDocument(item.document!.public_id)}>{openingDocument === item.document.public_id ? <LoadingIndicator label="Abriendo…" compact /> : <svg aria-hidden="true" viewBox="0 0 32 36" focusable="false"><path d="M4 1h16l8 8v26H4z" /><path d="M20 1v9h8" /><text x="7" y="26">PDF</text></svg>}</Button> : "Sin documento"}</td><td><Link className="icon-action-link" aria-label={item.reconciliation_status === "RECONCILED" ? "Editar causas" : "Evaluar ítem"} title={item.reconciliation_status === "RECONCILED" ? "Editar causas" : "Evaluar ítem"} to={`/items/${item.public_id}/evaluation?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`}>{item.reconciliation_status === "RECONCILED" ? <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M4 16.5V20h3.5L18 9.5 14.5 6 4 16.5Z" /><path d="m13.5 7 3.5 3.5" /></svg> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M9 5h6" /><path d="M9 3h6v4H9z" /><path d="M6 5H4v16h16V5h-2" /><path d="m8 13 2 2 5-5" /></svg>}</Link></td></tr>)}{!itemsQuery.isLoading && items.length === 0 && <tr><td colSpan={8}>No hay ítems para este gerente con los filtros seleccionados.</td></tr>}</tbody></table></div>
      <div className="pagination"><Button variant="secondary" size="sm" disabled={!hasPrevious || itemsQuery.isFetching} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>Anterior</Button><span>{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${total}` : "0 ítems"}</span><Button variant="secondary" size="sm" disabled={!hasNext || itemsQuery.isFetching} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Siguiente</Button></div>
    </section>
  </>;
}
