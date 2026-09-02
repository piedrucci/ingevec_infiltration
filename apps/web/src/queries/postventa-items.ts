import { queryOptions, useQuery } from "@tanstack/react-query";

import { getPostventaItems } from "../api";

export const postventaItemQueryKeys = {
  all: ["postventa-items"] as const,
  byProject: (projectId: string) => [...postventaItemQueryKeys.all, "project", projectId] as const,
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
