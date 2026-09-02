import { queryOptions, useQuery } from "@tanstack/react-query";

import { getProjects } from "../api";

export const projectQueryKeys = {
  all: ["projects"] as const,
  list: (search: string) => [...projectQueryKeys.all, "list", search] as const,
};

export function projectsQueryOptions(search: string) {
  return queryOptions({
    queryKey: projectQueryKeys.list(search),
    queryFn: () => getProjects(search),
  });
}

export function useProjects(search: string) {
  return useQuery(projectsQueryOptions(search));
}
