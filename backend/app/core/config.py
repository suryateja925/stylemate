from dataclasses import dataclass
from pathlib import Path
import os
import re
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./stylemate.db")
    frontend_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
    )
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_anon_key: str = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    ).strip()
    supabase_jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "").strip()
    supabase_service_role_key: str = (
        os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()
    supabase_storage_bucket: str = os.getenv("SUPABASE_STORAGE_BUCKET", "wardrobe-private").strip()
    storage_provider: str = os.getenv("MEDIA_STORAGE_PROVIDER", "local").lower().strip()
    allowed_hosts: tuple[str, ...] = tuple(
        host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
    )
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    ai_request_timeout_seconds: int = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "45"))
    media_root: Path = Path(os.getenv("MEDIA_ROOT", str(PROJECT_ROOT / "media")))
    ai_provider: str = os.getenv("AI_PROVIDER", "").lower().strip()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "").strip()
    weather_provider: str = os.getenv("WEATHER_PROVIDER", "").lower().strip()
    weather_api_key: str = os.getenv("WEATHER_API_KEY", "").strip()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate(self) -> None:
        if self.app_env not in {"development", "test", "production"}:
            raise RuntimeError("APP_ENV must be development, test, or production.")
        if not 1 <= self.max_upload_mb <= 25:
            raise RuntimeError("MAX_UPLOAD_MB must be between 1 and 25.")
        if not 1 <= self.ai_request_timeout_seconds <= 300:
            raise RuntimeError("AI_REQUEST_TIMEOUT_SECONDS must be between 1 and 300.")
        if self.storage_provider not in {"local", "supabase"}:
            raise RuntimeError("MEDIA_STORAGE_PROVIDER must be local or supabase.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,61}", self.supabase_storage_bucket):
            raise RuntimeError("SUPABASE_STORAGE_BUCKET must be a valid bucket name.")
        if self.storage_provider == "supabase":
            if not self.supabase_url or not self.supabase_service_role_key or not self.supabase_storage_bucket:
                raise RuntimeError("Supabase media storage requires SUPABASE_URL, SUPABASE_SECRET_KEY, and SUPABASE_STORAGE_BUCKET.")
        if self.is_production:
            if not self.database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
                raise RuntimeError("Production requires a PostgreSQL DATABASE_URL.")
            if parse_qs(urlparse(self.database_url).query).get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
                raise RuntimeError("Production DATABASE_URL must require TLS with sslmode=require or stronger.")
            if not self.supabase_url or not self.supabase_anon_key:
                raise RuntimeError("Production authentication requires SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY.")
            supabase_url = urlparse(self.supabase_url)
            if (
                supabase_url.scheme != "https"
                or not supabase_url.netloc
                or supabase_url.username
                or supabase_url.password
                or supabase_url.path
                or supabase_url.query
                or supabase_url.fragment
            ):
                raise RuntimeError("Production SUPABASE_URL must be an HTTPS project origin.")
            if self.storage_provider != "supabase":
                raise RuntimeError("Production requires MEDIA_STORAGE_PROVIDER=supabase.")
            if not self.allowed_hosts:
                raise RuntimeError("Production requires explicit ALLOWED_HOSTS.")
            if any("*" in host for host in self.allowed_hosts):
                raise RuntimeError("Production ALLOWED_HOSTS must not contain wildcard hosts.")
            if not self.frontend_origins:
                raise RuntimeError("Production FRONTEND_ORIGINS must contain at least one HTTPS origin.")
            for origin in self.frontend_origins:
                parsed_origin = urlparse(origin)
                hostname = parsed_origin.hostname or ""
                if (
                    parsed_origin.scheme != "https"
                    or not parsed_origin.netloc
                    or parsed_origin.username
                    or parsed_origin.password
                    or parsed_origin.path not in {"", "/"}
                    or parsed_origin.query
                    or parsed_origin.fragment
                    or "*" in origin
                    or hostname in {"localhost", "127.0.0.1", "::1"}
                ):
                    raise RuntimeError("Production FRONTEND_ORIGINS must contain only explicit HTTPS origins.")


settings = Settings()
settings.validate()
if settings.storage_provider == "local":
    settings.media_root.joinpath("uploads").mkdir(parents=True, exist_ok=True)
    settings.media_root.joinpath("crops").mkdir(parents=True, exist_ok=True)
