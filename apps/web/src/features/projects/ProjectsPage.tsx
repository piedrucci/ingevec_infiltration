import { type FormEvent, useState } from "react";

import { getDocumentPdf } from "../../api";
import { usePostventaItems } from "../../queries/postventa-items";
import { useProjects } from "../../queries/projects";
import type { Project } from "../../types";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat("es-CL").format(new Date(`${value}T00:00:00`)) : "-";

export function ProjectsPage() {
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [search, setSearch] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [documentError, setDocumentError] = useState<Error | null>(null);
  const [openingDocument, setOpeningDocument] = useState<string | null>(null);
  const projectsQuery = useProjects(projectSearch);
  const itemsQuery = usePostventaItems(selectedProject?.id ?? null);
  const projects = projectsQuery.data?.items ?? [];
  const items = itemsQuery.data?.items ?? [];

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

  const submitSearch = (event: FormEvent) => { event.preventDefault(); setSelectedProject(null); setProjectSearch(search); };
  return <>
    <section className="toolbar"><form onSubmit={submitSearch}><label htmlFor="search">Buscar proyecto</label><input id="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Ej. 712 o PAM" /><button type="submit">Buscar</button></form></section>
    <ErrorMessage error={documentError ?? projectsQuery.error ?? itemsQuery.error} />
    {(projectsQuery.isLoading || itemsQuery.isLoading) && <div className="loading-block"><LoadingIndicator label="Cargando información…" /></div>}
    <section className="card"><div className="section-title"><h2>Proyectos</h2><span>{projects.length} visibles</span></div><div className="table-wrap"><table><thead><tr><th>Obra</th><th>Proyecto</th><th>Tipología</th><th>Ubicación</th><th>Supervisor</th><th>Administrador de proyecto</th></tr></thead><tbody>{projects.map((project) => <tr key={project.public_id} className={selectedProject?.id === project.id ? "selected" : ""} onClick={() => setSelectedProject(project)}><td>{project.id}</td><td>{project.name}</td><td>{project.typology}</td><td>{project.location}</td><td>{project.supervisor}</td><td>{project.project_admin || "-"}</td></tr>)}</tbody></table></div></section>
    {selectedProject && <section className="card"><div className="section-title"><div><p className="eyebrow">OBRA {selectedProject.id}</p><h2>{selectedProject.name}</h2></div><span>Recepción: {formatDate(selectedProject.municipal_reception_date)}</span></div><div className="table-wrap"><table><thead><tr><th>Ítem</th><th>Observación</th><th>Clasificación</th><th>Tipo</th><th>Causa</th><th>Documento</th></tr></thead><tbody>{items.map((item) => <tr key={item.public_id}><td>{item.id}</td><td>{item.notes}</td><td>{item.classification}</td><td>{item.item_type}</td><td>{item.failure_cause?.display_name_es || "-"}</td><td>{item.document ? <button className="document-link" type="button" disabled={openingDocument === item.document.public_id} onClick={() => void openDocument(item.document!.public_id)}>{openingDocument === item.document.public_id ? <LoadingIndicator label="Abriendo…" compact /> : `${item.document.original_filename} · ${item.document.status}`}</button> : "Sin documento"}</td></tr>)}</tbody></table></div></section>}
  </>;
}
