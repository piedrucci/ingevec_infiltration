import os


os.environ.update({
    "APP_ENV": "development",
    "DATABASE_URL": "postgresql+psycopg://user:password@localhost/db",
    "NATS_URL": "nats://localhost:4222",
    "S3_ENDPOINT_URL": "http://localhost:8333",
    "S3_BUCKET": "test",
    "S3_ACCESS_KEY": "test",
    "S3_SECRET_KEY": "test",
    "GEMINI_API_KEY": "test",
    "GEMINI_MODEL": "gemini-test",
    "OIDC_ISSUER": "http://localhost:8080/realms/test",
    "OIDC_AUDIENCE": "capix-api",
    "OIDC_JWKS_URL": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
})
