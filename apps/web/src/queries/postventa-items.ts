import { queryOptions, useQuery } from "@tanstack/react-query";

import { getPostventaItems, getPostventaItemsByProjectManager } from "../api";

export const postventaItemQueryKeys = {
  all: ["postventa-items"] as const,
  byProject: (projectId: string) => [...postventaItemQueryKeys.all, "project", projectId] as const,
  byProjectManager: (projectManagerId: number, search: string, documentStatus: string, offset: number) =>
    [...postventaItemQueryKeys.all, "project-manager", projectManagerId, search, documentStatus, offset] as const,
};

export function postventaItemsQueryOptions(projectId: string) {
  return queryOptions({
    queryKey: postventaItemQueryKeys.byProject(projectId),
    queryFn: () => getPostventaItems(projectId),
  });
}

export function usePostventaItems(projectId: string | null) {
  return useQuery({
    ...postventaItemsQueryOptions(projectId ?? ""),
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
