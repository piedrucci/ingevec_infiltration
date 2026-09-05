import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DATABASE_URI"]
WTF_CSRF_ENABLED = True
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": False}

# Superset starts with a local bootstrap administrator. Keycloak OIDC is added
# after its dedicated client and redirect URI are configured for each domain.
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Gamma"
