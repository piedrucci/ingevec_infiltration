import { queryOptions, useQuery } from "@tanstack/react-query";

import { getDocument, getDocumentCandidates, getDocuments, getFailureCauseCategories, getFailureCauses, getUnassociatedItems } from "../../api";
import type { Document } from "../../types";

export const documentQueryKeys = {
  all: ["documents"] as const,
  list: (status: string) => [...documentQueryKeys.all, "list", status] as const,
  detail: (publicId: string) => [...documentQueryKeys.all, "detail", publicId] as const,
  candidates: (publicId: string) => [...documentQueryKeys.all, "candidates", publicId] as const,
  failureCauses: () => [...documentQueryKeys.all, "failure-causes"] as const,
  failureCauseCategories: () => [...documentQueryKeys.all, "failure-cause-categories"] as const,
};

const isActive = (document: Document) => document.status === "QUEUED" || document.status === "PROCESSING" || document.status === "UPLOADING";

export function useDocuments(status = "") {
  return useQuery({
    ...queryOptions({ queryKey: documentQueryKeys.list(status), queryFn: () => getDocuments(status) }),
    refetchInterval: (query) => query.state.data?.items.some(isActive) ? 3000 : false,
  });
}

export function useDocument(publicId: string | undefined) {
  return useQuery({ ...queryOptions({ queryKey: documentQueryKeys.detail(publicId ?? ""), queryFn: () => getDocument(publicId ?? "") }), enabled: Boolean(publicId), refetchInterval: (query) => query.state.data && isActive(query.state.data) ? 3000 : false });
}

export function useDocumentCandidates(publicId: string | undefined, enabled = true) {
  return useQuery({ ...queryOptions({ queryKey: documentQueryKeys.candidates(publicId ?? ""), queryFn: () => getDocumentCandidates(publicId ?? "") }), enabled: Boolean(publicId) && enabled });
}

export function useFailureCauses() {
  return useQuery(queryOptions({ queryKey: documentQueryKeys.failureCauses(), queryFn: getFailureCauses }));
}

export function useFailureCauseCategories() {
  return useQuery(queryOptions({ queryKey: documentQueryKeys.failureCauseCategories(), queryFn: getFailureCauseCategories }));
}

export function useUnassociatedItems(search: string) {
  return useQuery({
    ...queryOptions({ queryKey: ["postventa-items", "unassociated", search], queryFn: () => getUnassociatedItems(search) }),
    enabled: search.trim().length >= 2,
  });
}
