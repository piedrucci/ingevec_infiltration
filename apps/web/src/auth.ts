import Keycloak from "keycloak-js";
import { queryClient } from "./query-client";

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || "http://localhost:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM || "ingevec-development",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "ingevec-web",
});

let lastAnalyticsSession = "";

function clearAnalyticsState(): void {
  queryClient.removeQueries({ queryKey: ["analytics"] });
  const mutationCache = queryClient.getMutationCache();
  for (const mutation of mutationCache.findAll({ mutationKey: ["analytics"] })) {
    mutationCache.remove(mutation);
  }
}

export async function startAuthentication(): Promise<void> {
  await keycloak.init({ onLoad: "login-required", pkceMethod: "S256" });
  lastAnalyticsSession = analyticsSessionKey();
  keycloak.onAuthRefreshSuccess = () => {
    const nextSession = analyticsSessionKey();
    if (nextSession !== lastAnalyticsSession) {
      clearAnalyticsState();
      lastAnalyticsSession = nextSession;
    }
  };
  keycloak.onAuthRefreshError = clearAnalyticsState;
  keycloak.onAuthLogout = clearAnalyticsState;
}

export function isAdmin(): boolean {
  return keycloak.realmAccess?.roles.includes("admin") ?? false;
}

export function hasAnalyticsAccess(): boolean {
  const roles = keycloak.realmAccess?.roles ?? [];
  return roles.some((role) => ["superset_admin", "superset_viewer", "superset_dashboard_builder"].includes(role));
}

export function analyticsSessionKey(): string {
  return `${keycloak.subject ?? "unknown"}:${(keycloak.realmAccess?.roles ?? []).filter((role) => role.startsWith("superset_")).sort().join(",")}`;
}

export async function accessToken(): Promise<string> {
  await keycloak.updateToken(30);
  if (!keycloak.token) {
    throw new Error("La sesión no tiene un token de acceso válido.");
  }
  return keycloak.token;
}

export function logout(): Promise<void> {
  clearAnalyticsState();
  return keycloak.logout({ redirectUri: window.location.origin });
}
