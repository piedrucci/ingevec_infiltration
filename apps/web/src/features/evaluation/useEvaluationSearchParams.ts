import { useSearchParams } from "react-router-dom";

export type EvaluationSearchParams = {
  search: string;
  reconciliationStatus: "" | "PENDING" | "RECONCILED";
  documentFilter: "" | "true" | "false";
  offset: number;
  sortBy: "project_id" | "notes" | "reconciliation_status";
  sortDirection: "asc" | "desc";
};

const DEFAULT_PARAMS: EvaluationSearchParams = {
  search: "",
  reconciliationStatus: "PENDING",
  documentFilter: "",
  offset: 0,
  sortBy: "project_id",
  sortDirection: "asc",
};

export function useUrlSearchParams() {
  const [searchParams, setSearchParams] = useSearchParams();
  const updateUrlParams = (updates: Record<string, string | number | null | undefined>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === undefined || value === "" || value === 0) next.delete(key);
      else next.set(key, String(value));
    }
    setSearchParams(next);
  };
  return { searchParams, updateUrlParams };
}

export function useEvaluationSearchParams() {
  const { searchParams, updateUrlParams } = useUrlSearchParams();
  const requestedOffset = Number(searchParams.get("offset") ?? "0");
  const params: EvaluationSearchParams = {
    search: searchParams.get("q") ?? DEFAULT_PARAMS.search,
    reconciliationStatus: searchParams.get("status") === "RECONCILED" ? "RECONCILED" : searchParams.get("status") === "ALL" ? "" : DEFAULT_PARAMS.reconciliationStatus,
    documentFilter: searchParams.get("pdf") === "true" ? "true" : searchParams.get("pdf") === "false" ? "false" : DEFAULT_PARAMS.documentFilter,
    offset: Number.isSafeInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : DEFAULT_PARAMS.offset,
    sortBy: ["project_id", "notes", "reconciliation_status"].includes(searchParams.get("sort") ?? "") ? searchParams.get("sort") as EvaluationSearchParams["sortBy"] : DEFAULT_PARAMS.sortBy,
    sortDirection: searchParams.get("dir") === "desc" ? "desc" : DEFAULT_PARAMS.sortDirection,
  };

  const updateParams = (updates: Partial<EvaluationSearchParams>) => {
    const urlUpdates: Record<string, string | number | null> = {};
    if (updates.search !== undefined) urlUpdates.q = updates.search;
    if (updates.reconciliationStatus !== undefined) urlUpdates.status = updates.reconciliationStatus || "ALL";
    if (updates.documentFilter !== undefined) urlUpdates.pdf = updates.documentFilter;
    if (updates.sortBy !== undefined) urlUpdates.sort = updates.sortBy;
    if (updates.sortDirection !== undefined) urlUpdates.dir = updates.sortDirection;
    urlUpdates.offset = updates.offset ?? null;
    updateUrlParams(urlUpdates);
  };

  return { params, updateParams };
}
