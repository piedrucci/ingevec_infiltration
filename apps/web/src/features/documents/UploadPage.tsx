import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { uploadDocument } from "../../api";
import { LoadingIndicator } from "./components";
import { documentQueryKeys } from "./queries";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../../components/ui/card";

type UploadResult = { id: string; filename: string; outcome: "accepted" | "duplicate" | "failed"; message: string; documentId?: string };

export function UploadPage() {
  const queryClient = useQueryClient();
  const [results, setResults] = useState<UploadResult[]>([]);
  const [uploading, setUploading] = useState(false);
  const uploadFiles = async (files: File[]) => {
    const entries = files.map((file, index) => ({ id: `${file.name}-${file.size}-${file.lastModified}-${index}`, file }));
    setUploading(true); setResults(entries.map(({ id, file }) => ({ id, filename: file.name, outcome: "accepted", message: "Esperando carga…" })));
    let cursor = 0;
    const uploadNext = async () => {
      while (cursor < entries.length) {
        const entry = entries[cursor++];
        const { file } = entry;
        try {
          const document = await uploadDocument(file);
          setResults((current) => current.map((result) => result.id === entry.id ? { ...result, message: "En cola para procesamiento", documentId: document.public_id } : result));
        } catch (reason) {
          const detail = (reason as Error & { detail?: { code?: string; document_public_id?: string } }).detail;
          const duplicate = detail && typeof detail === "object" && detail.code === "DUPLICATE_DOCUMENT";
          setResults((current) => current.map((result) => result.id === entry.id ? { ...result, outcome: duplicate ? "duplicate" : "failed", message: duplicate ? "El contenido ya había sido cargado" : (reason instanceof Error ? reason.message : "La carga falló"), documentId: duplicate ? detail.document_public_id : undefined } : result));
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(3, entries.length) }, uploadNext));
    await queryClient.invalidateQueries({ queryKey: documentQueryKeys.all });
    setUploading(false);
  };
  return <Card className="page-card gap-0 overflow-hidden py-0"><CardHeader className="py-5"><p className="eyebrow">DOCUMENTOS</p><CardTitle>Cargar informes PDF</CardTitle><CardDescription>Máximo 5 MB por archivo.</CardDescription></CardHeader><CardContent className="px-0"><div className="upload-area"><p>Selecciona uno o más informes de filtración. Los archivos válidos se procesarán en segundo plano.</p><input aria-label="Seleccionar archivos PDF" type="file" accept="application/pdf,.pdf" multiple disabled={uploading} onChange={(event) => { const files = Array.from(event.target.files ?? []); if (files.length) void uploadFiles(files); event.currentTarget.value = ""; }} />{uploading && <LoadingIndicator label="Subiendo archivos…" compact />}<p className="muted">No se aceptará contenido duplicado, aunque tenga otro nombre.</p></div>{results.length > 0 && <div className="upload-results"><h3>Resultado del lote</h3>{results.map((result) => <div className={`upload-result ${result.outcome}`} key={result.id}><strong>{result.filename}</strong><span>{result.message}</span>{result.message === "Esperando carga…" && <LoadingIndicator label="En espera" compact />}{result.documentId && <Link to={`/documents/${result.documentId}/review`}>{result.outcome === "duplicate" ? "Ver documento existente" : "Ver estado"}</Link>}</div>)}</div>}</CardContent><CardFooter className="px-5 pb-5"><Link to="/documents">Ver historial de documentos</Link></CardFooter></Card>;
}
