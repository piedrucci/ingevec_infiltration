import { accessToken } from "./auth";
import type { PageResponse, PostventaItem, Project } from "./types";

async function request<T>(path: string): Promise<T> {
  const token = await accessToken();
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`La API respondió ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export function getProjects(search = ""): Promise<PageResponse<Project>> {
  const query = new URLSearchParams({ limit: "100", offset: "0" });
  if (search.trim()) query.set("search", search.trim());
  return request<PageResponse<Project>>(`/v1/projects?${query}`);
}

export function getPostventaItems(projectId: string): Promise<PageResponse<PostventaItem>> {
  const query = new URLSearchParams({ project_id: projectId, limit: "100", offset: "0" });
  return request<PageResponse<PostventaItem>>(`/v1/postventa-items?${query}`);
}
