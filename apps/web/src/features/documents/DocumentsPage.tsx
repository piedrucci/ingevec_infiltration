import { useState } from "react";
import { Link } from "react-router-dom";

import type { DocumentStatus } from "../../types";
import { DocumentResultIndicator, DocumentStatusBadge, ErrorMessage, LoadingIndicator } from "./components";
import { useDocuments } from "./queries";

const statuses: Array<[string, string]> = [["", "Todos"], ["QUEUED", "En cola"], ["PROCESSING", "Procesando"], ["MATCHED", "Asociados"], ["PENDING_REVIEW", "Revisión"], ["UNMATCHED", "Sin asociación"], ["FAILED", "Con error"]];
const pageSizes = [15, 25, 50] as const;
const dateTime = (value: string) => new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));

export function DocumentsPage() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [pageSize, setPageSize] = useState<number>(15);
  const [offset, setOffset] = useState(0);
  const documentsQuery = useDocuments(status, search, pageSize, offset);
  const documents = documentsQuery.data?.items ?? [];
  const total = documentsQuery.data?.page.total ?? 0;
  const hasPrevious = offset > 0;
  const hasNext = offset + pageSize < total;

  const changeStatus = (value: string) => {
    setStatus(value);
    setOffset(0);
  };

  const changePageSize = (value: number) => {
    setPageSize(value);
    setOffset(0);
  };

  const changeSearch = (value: string) => {
    setSearch(value);
    setOffset(0);
  };

  return <section className="card">
    <div className="section-title"><div><p className="eyebrow">DOCUMENTOS</p><h2>Historial de cargas</h2></div><Link className="button-link" to="/documents/upload">Cargar PDFs</Link></div>
    <div className="filters">
      <label>Buscar <input type="search" value={search} placeholder="Archivo o número de obra" onChange={(event) => changeSearch(event.target.value)} /></label>
      <label>Estado <select value={status} onChange={(event) => changeStatus(event.target.value)}>{statuses.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>Filas por página <select value={pageSize} onChange={(event) => changePageSize(Number(event.target.value))}>{pageSizes.map((size) => <option value={size} key={size}>{size}</option>)}</select></label>
      <span>{total} documentos</span>
    </div>
    <ErrorMessage error={documentsQuery.error} />
    {documentsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando documentos…" /></div>}
    <div className="table-wrap"><table><thead><tr><th>Archivo</th><th>Obra</th><th>Estado</th><th>Asociaciones</th><th>Fecha de carga</th><th>Resultado</th></tr></thead><tbody>{documents.map((document) => { const result = document.processing_error || (document.status === "MATCHED" ? "Procesado correctamente" : null); const projects = document.projects ?? []; const detectedProject = document.extracted_data?.project_number; const obra = projects.length ? projects.join(", ") : (detectedProject?.match(/^\s*(\d+)/)?.[1] || "-"); return <tr key={document.public_id}><td><Link to={`/documents/${document.public_id}/review`}>{document.original_filename}</Link></td><td>{obra}</td><td><DocumentStatusBadge status={document.status as DocumentStatus} /></td><td>{document.association_count}</td><td>{dateTime(document.uploaded_at)}</td><td>{result ? <DocumentResultIndicator message={result} error={Boolean(document.processing_error)} /> : "-"}</td></tr>; })}{!documentsQuery.isLoading && documents.length === 0 && <tr><td colSpan={6}>No hay documentos para este filtro.</td></tr>}</tbody></table></div>
    <div className="pagination"><button className="secondary" type="button" disabled={!hasPrevious || documentsQuery.isFetching} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}>Anterior</button><span>{total ? `${offset + 1}–${Math.min(offset + pageSize, total)} de ${total}` : "0 documentos"}</span><button className="secondary" type="button" disabled={!hasNext || documentsQuery.isFetching} onClick={() => setOffset((value) => value + pageSize)}>Siguiente</button></div>
  </section>;
}
