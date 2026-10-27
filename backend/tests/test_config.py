from dataclasses import replace

import pytest

from backend.app.core.config import Settings


def _production_settings(**overrides: object) -> Settings:
    settings = replace(
        Settings(),
        app_env="production",
        database_url="postgresql://stylemate:secret@db.example.com:5432/stylemate?sslmode=require",
        frontend_origins=("https://stylemate.example.com",),
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-test-key",
        supabase_service_role_key="server-test-key",
        supabase_storage_bucket="wardrobe-private",
        storage_provider="supabase",
        allowed_hosts=("api.stylemate.example.com",),
    )
    return replace(settings, **overrides)


def test_production_settings_require_and_accept_managed_https_services() -> None:
    _production_settings().validate()


def test_production_settings_reject_unencrypted_database_urls() -> None:
    with pytest.raises(RuntimeError, match="sslmode=require"):
        _production_settings(database_url="postgresql://stylemate:secret@db.example.com:5432/stylemate").validate()


def test_production_settings_reject_local_origins() -> None:
    with pytest.raises(RuntimeError, match="explicit HTTPS origins"):
        _production_settings(frontend_origins=("https://localhost:5173",)).validate()


def test_production_settings_reject_wildcard_hosts() -> None:
    with pytest.raises(RuntimeError, match="wildcard"):
        _production_settings(allowed_hosts=("*",)).validate()
