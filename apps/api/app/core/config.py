from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str = "postgresql+psycopg://jav:jav@localhost:5432/jav"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_documents: str = "jav-documents"
    # Separate PUBLIC-read bucket for profile/product photos -- never the
    # same bucket as documents, which must stay private. See core/storage.py.
    s3_bucket_media: str = "jav-media"
    s3_region: str = "eu-central-1"
    s3_use_ssl: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]

    # /backend/docs, /backend/redoc and /backend/openapi.json are reachable
    # directly from the internet (see infrastructure/nginx/nginx.conf) --
    # convenient for development but a full API-surface disclosure in a real
    # production deployment. Defaults to enabled here because this project's
    # only environment today IS the dev/demo one and docs/user-guide.md
    # already documents /backend/docs as a real, relied-upon feature; set
    # ENABLE_API_DOCS=false in .env for a real production deployment (see
    # docs/server-migration-guide.md).
    enable_api_docs: bool = True

    # SMTP for password-reset emails (see auth/service.py::request_password_reset).
    # Left unset (smtp_host empty) falls back to logging the reset link via the
    # audit trail instead of failing -- see docs/business-rules.md §Password reset.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "no-reply@jav.demo"
    smtp_use_tls: bool = True

    # Base URL the dashboard is reachable at, used to build the link inside a
    # password-reset email (the API has no other way to know its own public
    # hostname -- it's never addressed directly by end users, see nginx.conf).
    public_app_base_url: str = "http://localhost:3000"

    # Dove arrivano i messaggi scritti a JudoArteVida dal modulo di
    # /contactos (club/contact.py), oltre alla casella "Messaggi" della
    # console. Quelli a un club vanno all'email di contatto del club.
    jav_contact_email: str = "info@judoartevida.com"

    # L'assistente dell'area privata (javbot/assistant.py). Senza chiave
    # JAVBOT risponde come prima, con le parole chiave: niente si rompe.
    anthropic_api_key: str = ""
    javbot_model: str = "claude-opus-5-5"
    # Quanto ragiona prima di rispondere: per una chat "low" basta, e
    # costa meno; "medium" per risposte più ragionate sui documenti.
    javbot_effort: str = "low"
    # Il microfono di JAVBOT: il servizio Whisper interno (apps/stt). Vuoto
    # = niente microfono (il bottone non compare).
    stt_url: str = "http://stt:8001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
