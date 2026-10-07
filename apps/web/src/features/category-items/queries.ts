import { queryOptions, useQuery } from "@tanstack/react-query";
import { getCategoryCauses, getItemCategories } from "../../api";

export const itemCategoryQueryKeys = {
  categories: ["item-categories", "list"] as const,
  causes: (categoryCode: string) => ["item-categories", categoryCode, "causes"] as const,
};

export function useItemCategories() {
  return useQuery(queryOptions({ queryKey: itemCategoryQueryKeys.categories, queryFn: getItemCategories, staleTime: 5 * 60_000 }));
}

export function useCategoryCauses(categoryCode: string | null) {
  return useQuery({
    queryKey: itemCategoryQueryKeys.causes(categoryCode ?? ""),
    queryFn: () => getCategoryCauses(categoryCode!),
    enabled: Boolean(categoryCode),
    staleTime: 5 * 60_000,
  });
}
