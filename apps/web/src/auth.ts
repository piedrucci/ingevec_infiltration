import Keycloak from "keycloak-js";

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || "http://localhost:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM || "ingevec-development",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "ingevec-web",
});

export async function startAuthentication(): Promise<void> {
  await keycloak.init({ onLoad: "login-required", pkceMethod: "S256" });
}

export function isAdmin(): boolean {
  return keycloak.realmAccess?.roles.includes("admin") ?? false;
}

export async function accessToken(): Promise<string> {
  await keycloak.updateToken(30);
  if (!keycloak.token) {
    throw new Error("La sesión no tiene un token de acceso válido.");
  }
  return keycloak.token;
}

export function logout(): Promise<void> {
  return keycloak.logout({ redirectUri: window.location.origin });
}
