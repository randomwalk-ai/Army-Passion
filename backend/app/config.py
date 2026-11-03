"""Application settings, read from environment variables (and the .env file)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg://army:army_dev_password@localhost:5434/army_passion"
    )
    redis_url: str = "redis://localhost:6380/0"

    app_env: str = "development"
    timezone: str = "Asia/Kolkata"
    secret_key: str = "change-me-in-production"

    # Every external service is behind an interface; "mock" is the fake implementation.
    whatsapp_provider: str = "mock"
    speech_to_text_provider: str = "mock"
    translation_provider: str = "mock"
    llm_provider: str = "mock"
    esign_provider: str = "mock"
    geocoding_provider: str = "mock"
    storage_provider: str = "local"

    local_storage_path: str = "./storage"
    # Placeholders for the blob storage (DigitalOcean Spaces / any S3-compatible
    # store). Not connected yet: STORAGE_PROVIDER=s3 explains what is missing.
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "blr1"

    # Used when llm_provider is not "mock".
    llm_api_key: str = ""
    # Model names change and old ones get retired; leave blank to use the
    # default chosen in app/services/llm.py.
    llm_model: str = ""
    llm_timeout_seconds: float = 20.0


settings = Settings()
