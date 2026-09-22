import { queryOptions, useQuery } from "@tanstack/react-query";

import { getProjects, type ProjectSearchOptions } from "../api";

export const projectQueryKeys = {
  all: ["projects"] as const,
  list: (options: ProjectSearchOptions) => [...projectQueryKeys.all, "list", options] as const,
};

export function projectsQueryOptions(options: ProjectSearchOptions) {
  return queryOptions({
    queryKey: projectQueryKeys.list(options),
    queryFn: () => getProjects(options),
  });
}

export function useProjects(options: ProjectSearchOptions = {}) {
  return useQuery(projectsQueryOptions(options));
}
