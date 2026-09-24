import type { DocumentStatus } from "../../types";
import { Badge } from "../../components/ui/badge";
import { Alert, AlertDescription } from "../../components/ui/alert";

const labels: Record<DocumentStatus, string> = {
  UPLOADING: "Cargando", QUEUED: "En cola", PROCESSING: "Procesando", MATCHED: "Asociado",
  PENDING_REVIEW: "Requiere revisión", UNMATCHED: "Sin asociación", FAILED: "Error", QUARANTINED: "Cuarentena",
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const variant = status === "MATCHED" ? "success" : status === "FAILED" || status === "QUARANTINED" ? "destructive" : status === "PENDING_REVIEW" || status === "UNMATCHED" ? "warning" : "info";
  return <Badge variant={variant}>{labels[status]}</Badge>;
}

export function ReconciliationBadge({ reconciled }: { reconciled: boolean }) {
  return <Badge variant={reconciled ? "success" : "warning"}>{reconciled ? "Conciliado" : "Pendiente"}</Badge>;
}

export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <Alert variant="destructive" className="mx-5 mb-4 w-auto"><AlertDescription>{error instanceof Error ? error.message : "Ocurrió un error inesperado."}</AlertDescription></Alert> : null;
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
