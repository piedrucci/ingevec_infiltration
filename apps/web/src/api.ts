import { accessToken } from "./auth";
import type { DashboardSummary, Document, DocumentCandidateResponse, DocumentDetail, DocumentSummary, FailureCauseCategoryOption, FailureCauseOption, PageResponse, PostventaItem, Project } from "./types";

type ApiErrorDetail = string | { code?: string; document_public_id?: string; original_filename?: string };

async function request<T>(path: string): Promise<T> {
  const token = await accessToken();
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: ApiErrorDetail } | null;
    const detail = typeof body?.detail === "string" ? body.detail : `La API respondió ${response.status}.`;
    const error = new Error(detail) as Error & { detail?: ApiErrorDetail };
    error.detail = body?.detail;
    throw error;
  }
  return response.json() as Promise<T>;
}

async function requestBlob(path: string): Promise<Blob> {
  const token = await accessToken();
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`La API respondió ${response.status}.`);
  }
  return response.blob();
}

export function getProjects(search = ""): Promise<PageResponse<Project>> {
  const query = new URLSearchParams({ limit: "100", offset: "0" });
  if (search.trim()) query.set("search", search.trim());
  return request<PageResponse<Project>>(`/v1/projects?${query}`);
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/v1/dashboard/summary");
}

export function getPostventaItems(projectId: string): Promise<PageResponse<PostventaItem>> {
  const query = new URLSearchParams({ project_id: projectId, limit: "100", offset: "0" });
  return request<PageResponse<PostventaItem>>(`/v1/postventa-items?${query}`);
}

export function getUnassociatedItems(search = ""): Promise<PageResponse<PostventaItem>> {
  const query = new URLSearchParams({ unassociated: "true", limit: "50", offset: "0" });
  if (search.trim()) query.set("search", search.trim());
  return request<PageResponse<PostventaItem>>(`/v1/postventa-items?${query}`);
}

export function getDocumentPdf(documentPublicId: string): Promise<Blob> {
  return requestBlob(`/v1/documents/${documentPublicId}/content`);
}

export function uploadDocument(file: File): Promise<DocumentSummary> {
  const body = new FormData();
  body.set("file", file);
  return accessToken().then(async (token) => {
    const response = await fetch("/v1/documents/upload", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
      const error = new Error(`La carga fue rechazada (${response.status}).`) as Error & { detail?: unknown };
      error.detail = payload?.detail;
      throw error;
    }
    return response.json() as Promise<DocumentSummary>;
  });
}

export function getDocuments(status = ""): Promise<PageResponse<Document>> {
  const query = new URLSearchParams({ limit: "100", offset: "0" });
  if (status) query.set("document_status", status);
  return request<PageResponse<Document>>(`/v1/documents?${query}`);
}

export function getDocument(documentPublicId: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/v1/documents/${documentPublicId}`);
}

export function getDocumentCandidates(documentPublicId: string): Promise<DocumentCandidateResponse> {
  return request<DocumentCandidateResponse>(`/v1/documents/${documentPublicId}/candidates`);
}

export function getFailureCauses(): Promise<FailureCauseOption[]> {
  return request<FailureCauseOption[]>("/v1/documents/failure-causes");
}

export function getFailureCauseCategories(): Promise<FailureCauseCategoryOption[]> {
  return request<FailureCauseCategoryOption[]>("/v1/documents/failure-cause-categories");
}

export function createFailureCause(input: { code: string; displayNameEs: string; categoryCode: string; aliases: string[] }): Promise<FailureCauseOption> {
  return accessToken().then(async (token) => {
    const response = await fetch("/v1/documents/failure-causes", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ code: input.code, display_name_es: input.displayNameEs, category_code: input.categoryCode, aliases: input.aliases }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(payload?.detail || `No fue posible crear la causa (${response.status}).`);
    }
    return response.json() as Promise<FailureCauseOption>;
  });
}

export function associateDocument(documentPublicId: string, postventaItemPublicIds: string[], failureCauseCode: string): Promise<DocumentDetail> {
  return accessToken().then(async (token) => {
    const response = await fetch(`/v1/documents/${documentPublicId}/associations`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ postventa_item_public_ids: postventaItemPublicIds, failure_cause_code: failureCauseCode }),
    });
    if (!response.ok) throw new Error(`No fue posible guardar la asociación (${response.status}).`);
    return response.json() as Promise<DocumentDetail>;
  });
}
