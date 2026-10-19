import { queryOptions, useQuery } from "@tanstack/react-query";
import { getFailureCauseGroups, getGroupCategories } from "../../api";

export const failureCauseGroupQueryKeys = {
  groups: ["failure-cause-groups", "list"] as const,
  categories: (groupCode: string) => ["failure-cause-groups", groupCode, "categories"] as const,
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
