import { queryOptions, useQuery } from "@tanstack/react-query";

import { getPostventaItem, getPostventaItems, getPostventaItemsByProjectManager, searchPostventaItems, type PostventaItemSearchOptions } from "../api";

export const postventaItemQueryKeys = {
  all: ["postventa-items"] as const,
  byProject: (projectId: string) => [...postventaItemQueryKeys.all, "project", projectId] as const,
  byProjectManager: (projectManagerId: number, search: string, documentStatus: string, offset: number) =>
    [...postventaItemQueryKeys.all, "project-manager", projectManagerId, search, documentStatus, offset] as const,
  evaluationList: (options: PostventaItemSearchOptions) => [...postventaItemQueryKeys.all, "evaluation", options] as const,
  detail: (publicId: string) => [...postventaItemQueryKeys.all, "detail", publicId] as const,
};

export function postventaItemsQueryOptions(projectId: string, search = "") {
  return queryOptions({
    queryKey: [...postventaItemQueryKeys.byProject(projectId), search],
    queryFn: () => getPostventaItems(projectId, search),
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

export function usePostventaItems(projectId: string | null, search = "") {
  return useQuery({
    ...postventaItemsQueryOptions(projectId ?? "", search),
    enabled: projectId !== null,
  });
}

export function usePostventaItemsByProjectManager(
  projectManagerId: number | null,
  options: { search: string; documentStatus: string; offset: number },
) {
  return useQuery({
    queryKey: postventaItemQueryKeys.byProjectManager(projectManagerId ?? 0, options.search, options.documentStatus, options.offset),
    queryFn: () => getPostventaItemsByProjectManager(projectManagerId!, options),
    enabled: projectManagerId !== null,
  });
}
