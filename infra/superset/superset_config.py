import os
import re
from types import SimpleNamespace

import jwt
from flask import g
from flask_appbuilder.security.manager import AUTH_DB, AUTH_OAUTH
from superset.security import SupersetSecurityManager

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DATABASE_URI"]
WTF_CSRF_ENABLED = True
ENABLE_PROXY_FIX = True
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": False}

# Superset starts with a local bootstrap administrator. Keycloak OIDC is added
# after its dedicated client and redirect URI are configured for each domain.
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Public"


class KeycloakSecurityManager(SupersetSecurityManager):
    """Synchronize Keycloak roles/groups and enforce analytics scopes server-side."""

    _scope_pattern = re.compile(r"^/superset/(division|project)/([A-Za-z0-9_-]+)$")

    def oauth_user_info(self, provider, response=None):
        if provider != "keycloak":
            return super().oauth_user_info(provider, response)
        data = self.appbuilder.sm.oauth_remotes[provider].get("userinfo").json()
        token_claims = {}
        access_token = (response or {}).get("access_token") if isinstance(response, dict) else None
        if access_token:
            # Authlib has already completed the authorization-code exchange.
            # Read role/group claims from the access token because Keycloak's
            # userinfo endpoint does not expose realm_access by default.
            try:
                token_claims = jwt.decode(access_token, options={"verify_signature": False})
            except jwt.PyJWTError:
                token_claims = {}
        roles = [
            *data.get("realm_access", {}).get("roles", []),
            *token_claims.get("realm_access", {}).get("roles", []),
        ]
        groups = [*data.get("groups", []), *token_claims.get("groups", [])]
        email = data.get("email", "")
        # Reuse the local bootstrap account when its configured email logs in
        # through Keycloak. Otherwise FAB would try to create a second user
        # with the same email (the local account has a unique email index).
        bootstrap_email = os.environ.get("SUPERSET_ADMIN_EMAIL", "").strip().lower()
        username = "admin" if email.strip().lower() == bootstrap_email else data["sub"]
        return {
            "username": username, "email": email,
            "first_name": data.get("given_name", data.get("preferred_username", "Usuario")),
            "last_name": data.get("family_name", ""),
            "role_keys": [*set(roles), *set(groups)],
        }

    def get_roles_from_keys(self, role_keys):
        roles = super().get_roles_from_keys(role_keys)
        for key in role_keys:
            match = self._scope_pattern.fullmatch(key)
            if match:
                role_name = f"keycloak_{match.group(1)}_{match.group(2)}"
                roles.add(self.find_role(role_name) or self.add_role(role_name))
        return roles

    def get_rls_filters(self, table):
        filters = super().get_rls_filters(table)
        if table.schema != "analytics" or table.table_name != "postventa_item_dashboard":
            return filters
        role_names = {role.name for role in self.get_user_roles(g.user)}
        if "Admin" in role_names:
            return filters
        divisions = [name.removeprefix("keycloak_division_") for name in role_names if name.startswith("keycloak_division_")]
        projects = [name.removeprefix("keycloak_project_") for name in role_names if name.startswith("keycloak_project_")]
        clauses = []
        safe_divisions = [value for value in divisions if value.isdigit()]
        if safe_divisions:
            clauses.append("division_manager_id IN (" + ",".join(safe_divisions) + ")")
        if projects:
            safe_projects = [value for value in projects if re.fullmatch(r"[A-Za-z0-9_-]+", value)]
            if safe_projects:
                clauses.append("numero_obra IN (" + ",".join("'" + value + "'" for value in safe_projects) + ")")
        return [*filters, SimpleNamespace(clause="(" + " OR ".join(clauses) + ")" if clauses else "1 = 0", group_key=None)]


if os.environ.get("SUPERSET_OIDC_CLIENT_SECRET"):
    AUTH_TYPE = AUTH_OAUTH
    CUSTOM_SECURITY_MANAGER = KeycloakSecurityManager
    AUTH_ROLES_MAPPING = {
        "superset_admin": ["Admin"],
        "superset_viewer": ["Gamma", "Ingevec Viewer"],
    }
    AUTH_ROLES_SYNC_AT_LOGIN = True
    _public = os.environ["SUPERSET_OIDC_PUBLIC_URL"].rstrip("/")
    _internal = os.environ.get("SUPERSET_OIDC_INTERNAL_URL", _public).rstrip("/")
    _realm = os.environ["SUPERSET_OIDC_REALM"]
    OAUTH_PROVIDERS = [{"name": "keycloak", "icon": "fa-key", "token_key": "access_token",
        "remote_app": {"client_id": os.environ["SUPERSET_OIDC_CLIENT_ID"],
          "client_secret": os.environ["SUPERSET_OIDC_CLIENT_SECRET"],
          "api_base_url": f"{_internal}/realms/{_realm}/protocol/openid-connect/",
          "access_token_url": f"{_internal}/realms/{_realm}/protocol/openid-connect/token",
          "authorize_url": f"{_public}/realms/{_realm}/protocol/openid-connect/auth",
          # Authlib validates the OpenID Connect ID token after exchanging the
          # authorization code. These are metadata fields (not a nested
          # ``server_metadata`` mapping in the Authlib version Superset uses).
          # Browser-facing URLs stay public; server-to-server calls use Docker.
          "issuer": f"{_public}/realms/{_realm}",
          "userinfo_endpoint": f"{_internal}/realms/{_realm}/protocol/openid-connect/userinfo",
          "jwks_uri": f"{_internal}/realms/{_realm}/protocol/openid-connect/certs",
          # Do not silently reuse the previous Keycloak browser session. This
          # lets an administrator switch between Superset users locally.
          "authorize_params": {"prompt": "login"},
          "client_kwargs": {"scope": "openid profile email"}}}]
else:
    AUTH_TYPE = AUTH_DB
