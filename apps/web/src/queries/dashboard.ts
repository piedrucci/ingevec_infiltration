import { queryOptions, useQuery } from "@tanstack/react-query";

import { getDashboardProjectProgress, getDashboardSubcontractorProjects, getDashboardSubcontractors, getDashboardSummary } from "../api";

export const dashboardQueryKey = ["dashboard", "summary"] as const;
export const dashboardSubcontractorsQueryKey = ["dashboard", "subcontractors"] as const;

export const dashboardQueryOptions = queryOptions({
  queryKey: dashboardQueryKey,
  queryFn: getDashboardSummary,
  staleTime: 60_000,
  refetchInterval: 60_000,
});

export function useDashboardSummary() {
  return useQuery(dashboardQueryOptions);
}

export function useDashboardProjectProgress(options: { limit: number; offset: number; sortBy: string; sortDirection: "asc" | "desc" }) {
  return useQuery({
    queryKey: [...dashboardQueryKey, "projects", options],
    queryFn: () => getDashboardProjectProgress(options),
    staleTime: 60_000,
  });
}

export function useDashboardSubcontractors() {
  return useQuery({
    queryKey: dashboardSubcontractorsQueryKey,
    queryFn: getDashboardSubcontractors,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}

export function useDashboardSubcontractorProjects(subcontractorId: number | null) {
  return useQuery({
    queryKey: [...dashboardSubcontractorsQueryKey, subcontractorId, "projects"],
    queryFn: () => getDashboardSubcontractorProjects(subcontractorId!),
    enabled: subcontractorId !== null,
    staleTime: 60_000,
  });
}
