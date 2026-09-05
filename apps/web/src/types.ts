export type Page = { total: number; limit: number; offset: number };

export type Project = {
  id: string;
  public_id: string;
  name: string;
  typology: string;
  location: string;
  municipal_reception_date: string | null;
  supervisor: string;
  project_manager: string | null;
  project_admin: string | null;
};

export type DocumentSummary = {
  public_id: string;
  original_filename: string;
  status: string;
  uploaded_at: string;
  processed_at: string | null;
};

export type PostventaItem = {
  id: number;
  public_id: string;
  project_id: string;
  project_name: string;
  classification: string;
  item_type: string;
  notes: string;
  request_date: string | null;
  subcontractor: string | null;
  handled_by: string | null;
  failure_cause: { display_name_es: string; category_name_es: string } | null;
  document: DocumentSummary | null;
};

export type PageResponse<T> = { items: T[]; page: Page };

export type DocumentStatus = "UPLOADING" | "QUEUED" | "PROCESSING" | "MATCHED" | "PENDING_REVIEW" | "UNMATCHED" | "FAILED" | "QUARANTINED";

export type Document = DocumentSummary & {
  matching_confidence: number | null;
  extracted_data: Record<string, string | null> | null;
  extracted_failure_cause: string | null;
  processing_error: string | null;
  association_count: number;
};

export type DocumentAssociation = {
  postventa_item_public_id: string;
  postventa_item_id: number;
  project_id: string;
  project_name: string;
  notes: string;
  association_source: "AUTOMATIC" | "MANUAL";
  confidence: number | null;
  rationale: string | null;
};

export type DocumentDetail = Document & { associations: DocumentAssociation[] };

export type DocumentCandidate = {
  postventa_item_public_id: string;
  postventa_item_id: number;
  project_id: string;
  project_name: string;
  notes: string;
  score: number;
};

export type FailureCauseOption = {
  code: string;
  display_name_es: string;
  category_name_es: string;
};

export type FailureCauseCategoryOption = {
  code: string;
  display_name_es: string;
};
