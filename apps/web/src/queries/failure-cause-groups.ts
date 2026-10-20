import { queryOptions, useQuery } from "@tanstack/react-query";
import { getFailureCauseGroups, getGroupCategories, getGroupCategoryCauses } from "../api";

export const failureCauseGroupQueryKeys = {
  all: ["failure-cause-groups"] as const,
  groups: ["failure-cause-groups", "list"] as const,
  categories: (groupCode: string) => ["failure-cause-groups", groupCode, "categories"] as const,
  causes: (groupCode: string, categoryCode: string) => ["failure-cause-groups", groupCode, "categories", categoryCode, "causes"] as const,
};

export function useFailureCauseGroups() {
  return useQuery(queryOptions({ queryKey: failureCauseGroupQueryKeys.groups, queryFn: getFailureCauseGroups, staleTime: 5 * 60_000 }));
}

export function useGroupCategories(groupCode: string | null) {
  return useQuery({
    queryKey: failureCauseGroupQueryKeys.categories(groupCode ?? ""),
    queryFn: () => getGroupCategories(groupCode!),
    enabled: Boolean(groupCode),
    staleTime: 5 * 60_000,
  });
}

export function useGroupCategoryCauses(groupCode: string | null, categoryCode: string | null) {
  return useQuery({
    queryKey: failureCauseGroupQueryKeys.causes(groupCode ?? "", categoryCode ?? ""),
    queryFn: () => getGroupCategoryCauses(groupCode!, categoryCode!),
    enabled: Boolean(groupCode && categoryCode),
    staleTime: 5 * 60_000,
  });
}
