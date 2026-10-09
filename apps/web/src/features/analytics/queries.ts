import { useMutation, useQuery } from "@tanstack/react-query";

import { getAnalyticsDashboard, getAnalyticsGuestToken } from "../../api";
import { analyticsSessionKey } from "../../auth";

export const analyticsKeys = {
  dashboard: (session: string) => ["analytics", session, "dashboard"] as const,
};

export function useAnalyticsDashboard() {
  const session = analyticsSessionKey();
  return useQuery({ queryKey: analyticsKeys.dashboard(session), queryFn: getAnalyticsDashboard, staleTime: 60_000, retry: false });
}

export function useAnalyticsGuestToken() {
  return useMutation({ mutationKey: ["analytics", "guest-token"], mutationFn: getAnalyticsGuestToken, gcTime: 0 });
}
