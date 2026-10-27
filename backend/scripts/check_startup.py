"""Validate local StyleMate storage and configuration without starting a server."""

from backend.app.core.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.services.conversation import provider_status
from sqlalchemy import text


def main() -> int:
    try:
        if not settings.is_production:
            init_db()
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        if settings.storage_provider == "local":
            settings.media_root.joinpath("uploads").mkdir(parents=True, exist_ok=True)
            settings.media_root.joinpath("crops").mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"FAIL storage: {exc}")
        return 1

    status = provider_status()
    print(f"OK database: {settings.database_url}")
    if settings.storage_provider == "local":
        print(f"OK media_root: {settings.media_root.resolve()}")
    else:
        print(f"OK media_storage: Supabase bucket {settings.supabase_storage_bucket}")
    if status["configured"]:
        print(f"OK text_ai: {status['provider']}")
    else:
        print("WARN text_ai: not configured; chat, voice commands, and real scans will report a configuration error")
    print("OK startup validation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
