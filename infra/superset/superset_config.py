import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DATABASE_URI"]
WTF_CSRF_ENABLED = True
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": False}

# Keycloak OIDC is configured during deployment with the realm-specific client.
# Only the Keycloak `admin` role receives Superset Admin privileges.
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Gamma"

