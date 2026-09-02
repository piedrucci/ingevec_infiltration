from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    APP_ENV: str = Field(pattern="^(development|production)$")
    APP_NAME: str = "Capix Ingevec API"
    API_PREFIX: str = "/v1"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str
    NATS_URL: str
    S3_ENDPOINT_URL: AnyHttpUrl
    S3_REGION: str = "us-east-1"
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    GEMINI_API_KEY: str
    GEMINI_MODEL: str
    OIDC_ISSUER: AnyHttpUrl
    OIDC_AUDIENCE: str
    OIDC_JWKS_URL: AnyHttpUrl
    PRESIGNED_URL_TTL_SECONDS: int = Field(default=3600, ge=60, le=3600)
    MAX_EXCEL_SIZE_BYTES: int = Field(default=26_214_400, ge=1, le=26_214_400)
    MAX_PDF_SIZE_BYTES: int = Field(default=5_242_880, ge=1, le=5_242_880)
    PDF_SCAN_INTERVAL_SECONDS: int = Field(default=60, ge=10, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
