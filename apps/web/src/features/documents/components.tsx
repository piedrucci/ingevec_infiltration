import type { DocumentStatus } from "../../types";

const labels: Record<DocumentStatus, string> = {
  UPLOADING: "Cargando", QUEUED: "En cola", PROCESSING: "Procesando", MATCHED: "Asociado",
  PENDING_REVIEW: "Requiere revisión", UNMATCHED: "Sin asociación", FAILED: "Error", QUARANTINED: "Cuarentena",
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  return <span className={`status status-${status.toLowerCase()}`}>{labels[status]}</span>;
}

export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <p className="error" role="alert">{error instanceof Error ? error.message : "Ocurrió un error inesperado."}</p> : null;
}

export function LoadingIndicator({ label = "Cargando…", compact = false }: { label?: string; compact?: boolean }) {
  return <span className={`loading-indicator${compact ? " loading-indicator-compact" : ""}`} role="status" aria-live="polite">
    <span className="spinner" aria-hidden="true" />
    <span>{label}</span>
  </span>;
}
