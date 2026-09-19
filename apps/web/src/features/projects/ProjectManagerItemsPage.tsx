import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getDocumentPdf } from "../../api";
import { useDashboardSummary } from "../../queries/dashboard";
import { usePostventaItemsByProjectManager } from "../../queries/postventa-items";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

const PAGE_SIZE = 50;

export function ProjectManagerItemsPage() {
  const { projectManagerId: rawProjectManagerId } = useParams();
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
      <div className="filters"><label htmlFor="manager-search">Buscar <input id="manager-search" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} placeholder="Obra o descripción" /></label><label htmlFor="manager-status">Documento <select id="manager-status" value={documentStatus} onChange={(event) => { setDocumentStatus(event.target.value); setOffset(0); }}><option value="">Todos</option><option value="MATCHED">Asociados</option><option value="PENDING_REVIEW">Requieren revisión</option><option value="UNMATCHED">Sin asociación</option><option value="FAILED">Con error</option></select></label></div>
      <ErrorMessage error={documentError ?? summaryQuery.error ?? itemsQuery.error} />
      {itemsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando ítems…" /></div>}
      <div className="table-wrap"><table><thead><tr><th>Obra</th><th>Ítem</th><th>Observación</th><th>Clasificación</th><th>Tipo</th><th>Causas</th><th>Documento</th></tr></thead><tbody>{items.map((item) => <tr key={item.public_id}><td>{item.project_id} · {item.project_name}</td><td>{item.id}</td><td>{item.notes}</td><td>{item.classification}</td><td>{item.item_type}</td><td>{item.failure_causes.length ? item.failure_causes.map((cause) => <span className="cause-tag" key={cause.code}>{cause.display_name_es}</span>) : "Sin causa"}</td><td>{item.document ? <button className="document-link" type="button" disabled={openingDocument === item.document.public_id} onClick={() => void openDocument(item.document!.public_id)}>{openingDocument === item.document.public_id ? <LoadingIndicator label="Abriendo…" compact /> : `${item.document.original_filename} · ${item.document.status}`}</button> : "Sin documento"}</td></tr>)}{!itemsQuery.isLoading && items.length === 0 && <tr><td colSpan={7}>No hay ítems para este gerente con los filtros seleccionados.</td></tr>}</tbody></table></div>
      <div className="pagination"><button className="secondary" type="button" disabled={!hasPrevious || itemsQuery.isFetching} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>Anterior</button><span>{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${total}` : "0 ítems"}</span><button className="secondary" type="button" disabled={!hasNext || itemsQuery.isFetching} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Siguiente</button></div>
    </section>
  </>;
}
