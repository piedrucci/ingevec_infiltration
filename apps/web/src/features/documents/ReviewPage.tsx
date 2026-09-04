import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { associateDocument, getDocumentPdf } from "../../api";
import { DocumentStatusBadge, ErrorMessage } from "./components";
import { documentQueryKeys, useDocument, useDocumentCandidates, useFailureCauses, useUnassociatedItems } from "./queries";
import type { DocumentCandidate, DocumentStatus } from "../../types";

export function ReviewPage() {
  const { publicId } = useParams();
  const queryClient = useQueryClient();
  const documentQuery = useDocument(publicId);
  const document = documentQuery.data;
  const canReview = document?.status === "PENDING_REVIEW" || document?.status === "UNMATCHED";
  const candidatesQuery = useDocumentCandidates(publicId, canReview);
  const causesQuery = useFailureCauses();
  const [selected, setSelected] = useState<string[]>([]);
  const [causeCode, setCauseCode] = useState("");
  const [itemSearch, setItemSearch] = useState("");
  const searchedItemsQuery = useUnassociatedItems(itemSearch);
  const candidates = useMemo<DocumentCandidate[]>(() => {
    const suggested = candidatesQuery.data?.items ?? [];
    const searched = (searchedItemsQuery.data?.items ?? []).map((item) => ({ postventa_item_public_id: item.public_id, postventa_item_id: item.id, project_id: item.project_id, project_name: item.project_name, notes: item.notes, score: 0 }));
    return [...suggested, ...searched.filter((item) => !suggested.some((candidate) => candidate.postventa_item_public_id === item.postventa_item_public_id))];
  }, [candidatesQuery.data, searchedItemsQuery.data]);
  const defaultCause = useMemo(() => causesQuery.data?.find((cause) => document?.extracted_failure_cause?.toLocaleLowerCase("es-CL").includes(cause.display_name_es.toLocaleLowerCase("es-CL")))?.code ?? "", [causesQuery.data, document?.extracted_failure_cause]);
  const mutation = useMutation({ mutationFn: () => associateDocument(publicId!, selected, causeCode || defaultCause), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: documentQueryKeys.all }); setSelected([]); } });
  const toggleItem = (id: string, checked: boolean) => setSelected((current) => checked ? [...current, id] : current.filter((selectedId) => selectedId !== id));
  const openPdf = async () => { if (!publicId) return; const preview = window.open("", "_blank"); try { const blob = await getDocumentPdf(publicId); const url = URL.createObjectURL(blob); if (preview) preview.location.href = url; window.setTimeout(() => URL.revokeObjectURL(url), 60_000); } catch { preview?.close(); } };
  if (documentQuery.isLoading) return <p className="loading">Cargando documento…</p>;
  if (!document) return <><ErrorMessage error={documentQuery.error} /><Link to="/documents">Volver al historial</Link></>;
  const chosenCause = causeCode || defaultCause;
  return <section className="review-layout">
    <section className="card"><div className="section-title"><div><p className="eyebrow">DOCUMENTO</p><h2>{document.original_filename}</h2></div><DocumentStatusBadge status={document.status as DocumentStatus} /></div><div className="detail-grid"><div><strong>Cargado</strong><p>{new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short" }).format(new Date(document.uploaded_at))}</p></div><div><strong>Proyecto detectado</strong><p>{document.extracted_data?.project_number || "No detectado"} {document.extracted_data?.project_name || ""}</p></div><div><strong>Lugar</strong><p>{document.extracted_data?.infiltration_location || "No detectado"}</p></div><div><strong>Causa extraída</strong><p>{document.extracted_failure_cause || "No detectada"}</p></div></div><button type="button" onClick={() => void openPdf()}>Abrir PDF</button>{document.processing_error && <ErrorMessage error={new Error(document.processing_error)} />}</section>
    <section className="card"><div className="section-title"><h2>Asociaciones</h2><span>{document.associations.length}</span></div>{document.associations.length ? <ul className="association-list">{document.associations.map((association) => <li key={association.postventa_item_public_id}><strong>{association.project_id} · Ítem {association.postventa_item_id}</strong><span>{association.notes}</span><small>{association.association_source === "MANUAL" ? "Manual" : "Automática"}</small></li>)}</ul> : <p className="empty-state">Aún no existen asociaciones.</p>}</section>
    {canReview && <section className="card"><div className="section-title"><div><p className="eyebrow">REVISIÓN MANUAL</p><h2>Seleccionar ítems y causa</h2></div><span>{candidates.length} candidatos</span></div><ErrorMessage error={candidatesQuery.error ?? causesQuery.error ?? searchedItemsQuery.error ?? mutation.error} /><div className="review-form"><label>Causa normalizada<select value={causeCode} onChange={(event) => setCauseCode(event.target.value)}><option value="">Selecciona una causa</option>{causesQuery.data?.map((cause) => <option key={cause.code} value={cause.code}>{cause.category_name_es} · {cause.display_name_es}</option>)}</select></label><label>Buscar otro ítem libre<input value={itemSearch} onChange={(event) => setItemSearch(event.target.value)} placeholder="Obra, proyecto u observación" /></label><div className="table-wrap"><table><thead><tr><th></th><th>Obra</th><th>Ítem</th><th>Observación</th><th>Similitud</th></tr></thead><tbody>{candidates.map((candidate) => <tr key={candidate.postventa_item_public_id}><td><input aria-label={`Seleccionar ítem ${candidate.postventa_item_id}`} type="checkbox" checked={selected.includes(candidate.postventa_item_public_id)} onChange={(event) => toggleItem(candidate.postventa_item_public_id, event.target.checked)} /></td><td>{candidate.project_id} · {candidate.project_name}</td><td>{candidate.postventa_item_id}</td><td>{candidate.notes}</td><td>{candidate.score ? `${Math.round(candidate.score * 100)}%` : "Manual"}</td></tr>)}{!candidates.length && <tr><td colSpan={5}>No hubo candidatos. Busca un ítem libre para asociarlo manualmente.</td></tr>}</tbody></table></div><button type="button" disabled={!selected.length || !chosenCause || mutation.isPending} onClick={() => mutation.mutate()}>Confirmar asociación manual</button></div></section>}
    <Link to="/documents">Volver al historial</Link>
  </section>;
}
