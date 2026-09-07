import { useState } from "react";
import { Link } from "react-router-dom";

import type { DocumentStatus } from "../../types";
import { DocumentStatusBadge, ErrorMessage, LoadingIndicator } from "./components";
import { useDocuments } from "./queries";

const statuses: Array<[string, string]> = [["", "Todos"], ["QUEUED", "En cola"], ["PROCESSING", "Procesando"], ["MATCHED", "Asociados"], ["PENDING_REVIEW", "Revisión"], ["UNMATCHED", "Sin asociación"], ["FAILED", "Con error"]];
const dateTime = (value: string) => new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));

export function DocumentsPage() {
  const [status, setStatus] = useState("");
  const documentsQuery = useDocuments(status);
  const documents = documentsQuery.data?.items ?? [];
  return <section className="card"><div className="section-title"><div><p className="eyebrow">DOCUMENTOS</p><h2>Historial de cargas</h2></div><Link className="button-link" to="/documents/upload">Cargar PDFs</Link></div><div className="filters"><label>Estado <select value={status} onChange={(event) => setStatus(event.target.value)}>{statuses.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><span>{documentsQuery.data?.page.total ?? 0} documentos</span></div><ErrorMessage error={documentsQuery.error} />{documentsQuery.isLoading && <div className="loading-block"><LoadingIndicator label="Cargando documentos…" /></div>}<div className="table-wrap"><table><thead><tr><th>Archivo</th><th>Estado</th><th>Asociaciones</th><th>Fecha de carga</th><th>Resultado</th></tr></thead><tbody>{documents.map((document) => <tr key={document.public_id}><td><Link to={`/documents/${document.public_id}/review`}>{document.original_filename}</Link></td><td><DocumentStatusBadge status={document.status as DocumentStatus} /></td><td>{document.association_count}</td><td>{dateTime(document.uploaded_at)}</td><td>{document.processing_error || (document.status === "MATCHED" ? "Procesado correctamente" : "-")}</td></tr>)}{!documentsQuery.isLoading && documents.length === 0 && <tr><td colSpan={5}>No hay documentos para este filtro.</td></tr>}</tbody></table></div></section>;
}
