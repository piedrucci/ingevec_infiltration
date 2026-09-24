import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { createFailureCause, removePostventaItemDocument, replacePostventaItemFailureCauses } from "../../api";
import { postventaItemQueryKeys, usePostventaItem } from "../../queries/postventa-items";
import { useFailureCauseCategories, useFailureCauses, documentQueryKeys } from "../documents/queries";
import { ErrorMessage, LoadingIndicator, ReconciliationBadge } from "../documents/components";
import { Button } from "../../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";

const suggestedCode = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "");

export function ItemEvaluationPage() {
  const { publicId } = useParams();
  const [searchParams] = useSearchParams();
  const requestedReturnTo = searchParams.get("returnTo");
  const returnTo = requestedReturnTo && requestedReturnTo.startsWith("/") && !requestedReturnTo.startsWith("//") ? requestedReturnTo : "/items/evaluation";
  const queryClient = useQueryClient();
  const itemQuery = usePostventaItem(publicId);
  const causesQuery = useFailureCauses();
  const categoriesQuery = useFailureCauseCategories();
  const [causeCodes, setCauseCodes] = useState<string[]>([]);
  const [isAddingCause, setIsAddingCause] = useState(false);
  const [newCauseName, setNewCauseName] = useState("");
  const [newCauseCode, setNewCauseCode] = useState("");
  const [newCauseCategory, setNewCauseCategory] = useState("");
  const [newCauseAliases, setNewCauseAliases] = useState("");
  const item = itemQuery.data;

  useEffect(() => {
    if (item) setCauseCodes(item.failure_causes.map((cause) => cause.code));
  }, [item?.public_id]);

  const saveMutation = useMutation({
    mutationFn: (codes: string[]) => replacePostventaItemFailureCauses(publicId!, codes),
    onSuccess: async (updated) => {
      setCauseCodes(updated.failure_causes.map((cause) => cause.code));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: postventaItemQueryKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
  });
  const removeDocumentMutation = useMutation({
    mutationFn: () => removePostventaItemDocument(publicId!, item!.document!.public_id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: postventaItemQueryKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
  });
  const createCauseMutation = useMutation({
    mutationFn: () => createFailureCause({ code: newCauseCode, displayNameEs: newCauseName, categoryCode: newCauseCategory, aliases: newCauseAliases.split(",").map((alias) => alias.trim()).filter(Boolean) }),
    onSuccess: async (cause) => {
      setCauseCodes((current) => current.includes(cause.code) ? current : [...current, cause.code]);
      setNewCauseName(""); setNewCauseCode(""); setNewCauseCategory(""); setNewCauseAliases(""); setIsAddingCause(false);
      await queryClient.invalidateQueries({ queryKey: documentQueryKeys.failureCauses() });
    },
  });

  if (itemQuery.isLoading) return <div className="loading-block"><LoadingIndicator label="Cargando ítem…" /></div>;
  if (!item) return <><ErrorMessage error={itemQuery.error} /><Link to="/items/evaluation">Volver a evaluación</Link></>;
  const clearCauses = () => { if (window.confirm("¿Quitar todas las causas? El ítem volverá a estado pendiente de conciliación.")) saveMutation.mutate([]); };
  const removeDocument = () => { if (window.confirm("¿Desasociar este PDF del ítem? El archivo no se elimina; volverá a revisión manual si no está vinculado a otro ítem.")) removeDocumentMutation.mutate(); };

  return <section className="review-layout">
    <section className="card"><div className="section-title"><div><Link className="back-link" to={returnTo}>← Volver a evaluación</Link><p className="eyebrow">OBRA {item.project_id} · ÍTEM {item.id}</p><h2>{item.project_name}</h2></div><ReconciliationBadge reconciled={item.reconciliation_status === "RECONCILED"} /></div><div className="detail-grid"><div className="detail-grid-full"><strong>Observación</strong><p>{item.notes}</p></div><div><strong>Clasificación</strong><p>{item.classification}</p></div><div><strong>Tipo</strong><p>{item.item_type}</p></div><div><strong>PDF asociado</strong><p>{item.has_document ? (item.document ? <span className="pdf-association-action"><Link to={`/documents/${item.document.public_id}/review`}>{item.document.original_filename}</Link><Button variant="ghost" size="icon" className="icon-danger-action" aria-label="Desasociar PDF" title="Desasociar PDF" disabled={removeDocumentMutation.isPending} onClick={removeDocument}>{removeDocumentMutation.isPending ? <LoadingIndicator label="Desasociando…" compact /> : <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="m10 14 4-4" /><path d="m8.5 8.5-1-1a3 3 0 0 0-4.25 4.25l2.5 2.5A3 3 0 0 0 10 14.5l1-1" /><path d="m15.5 15.5 1 1a3 3 0 0 0 4.25-4.25l-2.5-2.5A3 3 0 0 0 14 9.5l-1 1" /></svg>}</Button></span> : "Sí") : "No"}</p></div></div><ErrorMessage error={removeDocumentMutation.error} /></section>
    <section className="card"><div className="section-title"><div><p className="eyebrow">CONCILIACIÓN DIRECTA</p><h2>Causas de falla</h2></div><span>{causeCodes.length} seleccionada{causeCodes.length === 1 ? "" : "s"}</span></div><div className="review-form"><ErrorMessage error={causesQuery.error ?? categoriesQuery.error ?? saveMutation.error ?? createCauseMutation.error} /><label>Causas normalizadas<Select value={causeCodes[0] ?? "__none__"} onValueChange={(value) => { if (value !== "__none__") setCauseCodes((current) => current.includes(value) ? current.filter((code) => code !== value) : [...current, value]); }}><SelectTrigger><SelectValue placeholder="Selecciona causas" /></SelectTrigger><SelectContent><SelectItem value="__none__">Selecciona una causa</SelectItem>{causesQuery.data?.map((cause) => <SelectItem key={cause.code} value={cause.code}>{cause.category_name_es} · {cause.display_name_es}</SelectItem>)}</SelectContent></Select></label><p className="muted">Selecciona una causa a la vez; vuelve a abrir el menú para agregar o quitar otras.</p><div className="evaluation-actions"><Button disabled={!causeCodes.length || saveMutation.isPending} onClick={() => saveMutation.mutate(causeCodes)}>{saveMutation.isPending ? <LoadingIndicator label="Guardando…" compact /> : "Guardar causas"}</Button>{item.reconciliation_status === "RECONCILED" && <Button variant="secondary" disabled={saveMutation.isPending} onClick={clearCauses}>Quitar todas las causas</Button>}</div><Button variant="secondary" className="inline-action" onClick={() => setIsAddingCause((current) => !current)}>{isAddingCause ? "Cancelar nueva causa" : "Agregar nueva causa"}</Button>{isAddingCause && <fieldset className="new-cause-form"><legend>Nueva causa normalizada</legend><label>Nombre visible en español<input value={newCauseName} onChange={(event) => { setNewCauseName(event.target.value); setNewCauseCode(suggestedCode(event.target.value)); }} /></label><label>Código para BI<input value={newCauseCode} onChange={(event) => setNewCauseCode(suggestedCode(event.target.value))} /></label><label>Categoría<Select value={newCauseCategory || "__none__"} onValueChange={(value) => setNewCauseCategory(value === "__none__" ? "" : value)}><SelectTrigger><SelectValue placeholder="Selecciona una categoría" /></SelectTrigger><SelectContent><SelectItem value="__none__">Selecciona una categoría</SelectItem>{categoriesQuery.data?.map((category) => <SelectItem key={category.code} value={category.code}>{category.display_name_es}</SelectItem>)}</SelectContent></Select></label><label>Alias de detección (separados por coma)<input value={newCauseAliases} onChange={(event) => setNewCauseAliases(event.target.value)} /></label><Button disabled={!newCauseName || !newCauseCode || !newCauseCategory || createCauseMutation.isPending} onClick={() => createCauseMutation.mutate()}>{createCauseMutation.isPending ? <LoadingIndicator label="Creando causa…" compact /> : "Crear y seleccionar causa"}</Button></fieldset>}</div></section>
  </section>;
}
