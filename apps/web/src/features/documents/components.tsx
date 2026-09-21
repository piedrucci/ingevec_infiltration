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

export function DocumentResultIndicator({ message, error = false }: { message: string; error?: boolean }) {
  return <span
    className={`result-icon${error ? " result-icon-error" : " result-icon-success"}`}
    role="img"
    aria-label={message}
    title={message}
  >
    <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
      {error ? <>
        <path d="M12 3 2.7 20h18.6L12 3Z" />
        <path d="M12 9v5M12 17h.01" className="result-icon-mark" />
      </> : <>
        <circle cx="12" cy="12" r="9" />
        <path d="m8 12 2.5 2.5L16 9" className="result-icon-mark" />
      </>}
    </svg>
  </span>;
}
