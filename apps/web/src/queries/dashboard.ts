import { queryOptions, useQuery } from "@tanstack/react-query";

import { getDashboardSummary } from "../api";

export const dashboardQueryKey = ["dashboard", "summary"] as const;

export const dashboardQueryOptions = queryOptions({
  queryKey: dashboardQueryKey,
  queryFn: getDashboardSummary,
  staleTime: 60_000,
  refetchInterval: 60_000,
});

export function useDashboardSummary() {
  return useQuery(dashboardQueryOptions);
}
