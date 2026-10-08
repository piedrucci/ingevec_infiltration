import { queryOptions, useQuery } from "@tanstack/react-query";

import { getCategoryItems, getPostventaItem, getPostventaItems, getPostventaItemsByProjectManager, searchPostventaItems, type PostventaItemSearchOptions } from "../api";

export const postventaItemQueryKeys = {
  all: ["postventa-items"] as const,
  byProject: (projectId: string, search: string, limit: number, offset: number) => [...postventaItemQueryKeys.all, "project", projectId, search, limit, offset] as const,
  byProjectManager: (projectManagerId: number, options: { search: string; documentStatus: string; offset: number; sortBy: string; sortDirection: string }) =>
    [...postventaItemQueryKeys.all, "project-manager", projectManagerId, options] as const,
  evaluationList: (options: PostventaItemSearchOptions) => [...postventaItemQueryKeys.all, "evaluation", options] as const,
  detail: (publicId: string) => [...postventaItemQueryKeys.all, "detail", publicId] as const,
  byCategory: (categoryCode: string, causeCode: string) => [...postventaItemQueryKeys.all, "category", categoryCode, causeCode] as const,
};

export function postventaItemsQueryOptions(projectId: string, search = "", options: { limit?: number; offset?: number; sortBy?: "project_id" | "notes" | "reconciliation_status"; sortDirection?: "asc" | "desc" } = {}) {
  const limit = options.limit ?? 10;
  const offset = options.offset ?? 0;
  const sortBy = options.sortBy ?? "project_id";
  const sortDirection = options.sortDirection ?? "asc";
  return queryOptions({
    queryKey: [...postventaItemQueryKeys.byProject(projectId, search, limit, offset), sortBy, sortDirection],
    queryFn: () => getPostventaItems(projectId, search, { limit, offset, sortBy, sortDirection }),
  });
}

export type CategoryItemSearchOptions = { causeCode: string | null; search: string; pageNumber: number; sortBy: "project_id" | "project_name" | "notes"; sortDirection: "asc" | "desc"; pageSize?: number };

export function useItemsByCategory(categoryCode: string | null, options: CategoryItemSearchOptions) {
  return useQuery({
    queryKey: [...postventaItemQueryKeys.byCategory(categoryCode ?? "", options.causeCode ?? ""), options],
    queryFn: () => getCategoryItems(categoryCode!, {
      causeCode: options.causeCode ?? undefined,
      search: options.search,
      sortBy: options.sortBy,
      sortDirection: options.sortDirection,
      limit: options.pageSize ?? 10,
      offset: (options.pageNumber - 1) * (options.pageSize ?? 10),
    }),
    enabled: Boolean(categoryCode),
  });
}

export function useEvaluationItems(options: PostventaItemSearchOptions) {
  return useQuery({
    queryKey: postventaItemQueryKeys.evaluationList(options),
    queryFn: () => searchPostventaItems(options),
  });
}

export function usePostventaItem(publicId: string | undefined) {
  return useQuery({
    queryKey: postventaItemQueryKeys.detail(publicId ?? ""),
    queryFn: () => getPostventaItem(publicId ?? ""),
    enabled: Boolean(publicId),
  });
}

export function usePostventaItems(projectId: string | null, search = "", options: { limit?: number; offset?: number; sortBy?: "project_id" | "notes" | "reconciliation_status"; sortDirection?: "asc" | "desc" } = {}) {
  return useQuery({
    ...postventaItemsQueryOptions(projectId ?? "", search, options),
    enabled: projectId !== null,
  });
}

export function usePostventaItemsByProjectManager(
  projectManagerId: number | null,
  options: { search: string; documentStatus: string; offset: number; sortBy: "project_id" | "notes"; sortDirection: "asc" | "desc" },
) {
  return useQuery({
    queryKey: postventaItemQueryKeys.byProjectManager(projectManagerId ?? 0, options),
    queryFn: () => getPostventaItemsByProjectManager(projectManagerId!, options),
    enabled: projectManagerId !== null,
  });
}
