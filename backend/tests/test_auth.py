from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from backend.app.api import routes
from backend.app.models import ApiRateLimit, DeletedAccount, UserProfile
from backend.app.storage import MediaStorageError
from backend.app.services.rate_limit import enforce_rate_limit


JWT_SECRET = "unit-test-signing-secret-that-is-never-used-outside-tests"
SUPABASE_URL = "https://example.supabase.co"
USER_ID = "c5c6e2b9-5201-4fd8-a0fb-020bb91284dc"


def _settings(app_env: str = "production") -> SimpleNamespace:
    return SimpleNamespace(
        app_env=app_env,
        is_production=app_env == "production",
        supabase_url=SUPABASE_URL,
        supabase_jwt_secret=JWT_SECRET,
    )


def _token(*, user_id: str = USER_ID, expires_in: timedelta = timedelta(minutes=5)) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": f"{SUPABASE_URL}/auth/v1",
            "aud": "authenticated",
            "iat": now,
            "exp": now + expires_in,
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def _active_database() -> SimpleNamespace:
    return SimpleNamespace(get=lambda _model, _key: None)


def test_current_user_id_accepts_a_verified_supabase_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "settings", _settings())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_token())

    assert routes.current_user_id(credentials=credentials, x_user_id="attacker-selected-id", db=_active_database()) == USER_ID


def test_current_user_id_rejects_expired_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "settings", _settings())
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=_token(expires_in=timedelta(seconds=-5)),
    )

    with pytest.raises(HTTPException) as result:
        routes.current_user_id(credentials=credentials, x_user_id=None, db=_active_database())

    assert result.value.status_code == 401


def test_current_user_id_rejects_unsigned_local_identity_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "settings", _settings())

    with pytest.raises(HTTPException) as result:
        routes.current_user_id(credentials=None, x_user_id=USER_ID, db=_active_database())

    assert result.value.status_code == 401


def test_current_user_id_allows_local_identity_only_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "settings", _settings(app_env="development"))

    assert routes.current_user_id(credentials=None, x_user_id="local-test-user", db=_active_database()) == "local-test-user"


def test_authenticated_api_response_sets_private_security_headers(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]


def test_rate_limit_is_atomic_scoped_and_returns_retry_after(client) -> None:
    with client.app.state.testing_session_factory() as db:
        enforce_rate_limit(db, USER_ID, "test", limit=1, window_seconds=60)
        enforce_rate_limit(db, "another-user", "test", limit=1, window_seconds=60)
        with pytest.raises(HTTPException) as result:
            enforce_rate_limit(db, USER_ID, "test", limit=1, window_seconds=60)
        assert result.value.status_code == 429
        assert 1 <= int(result.value.headers["Retry-After"]) <= 60
        assert db.query(ApiRateLimit).count() == 2


def test_current_user_id_rejects_a_malformed_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "settings", _settings())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")

    with pytest.raises(HTTPException) as result:
        routes.current_user_id(credentials=credentials, x_user_id=None, db=_active_database())

    assert result.value.status_code == 401


def test_delete_account_removes_only_the_authenticated_user_data(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_user_id = "local-another-user"
    client.get("/api/profile", headers={"X-User-Id": USER_ID})
    client.get("/api/profile", headers={"X-User-Id": other_user_id})
    monkeypatch.setattr(
        routes,
        "settings",
        SimpleNamespace(
            is_production=False,
            storage_provider="supabase",
            supabase_service_role_key="test-service-key",
        ),
    )
    removed_objects: list[str] = []
    deleted_auth_users: list[str] = []
    monkeypatch.setattr(routes, "delete_user_objects", removed_objects.append)
    monkeypatch.setattr(routes, "delete_auth_user", deleted_auth_users.append)

    response = client.delete("/api/account", headers={"X-User-Id": USER_ID})

    assert response.status_code == 204
    assert removed_objects == [USER_ID]
    assert deleted_auth_users == [USER_ID]
    with client.app.state.testing_session_factory() as db:
        assert db.get(UserProfile, USER_ID) is None
        assert db.scalar(select(UserProfile).where(UserProfile.id == other_user_id)) is not None
        assert db.get(DeletedAccount, USER_ID) is not None
    assert client.get("/api/profile", headers={"X-User-Id": USER_ID}).status_code == 401


def test_delete_account_keeps_database_data_when_storage_cleanup_fails(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.get("/api/profile", headers={"X-User-Id": USER_ID})
    monkeypatch.setattr(
        routes,
        "settings",
        SimpleNamespace(
            is_production=False,
            storage_provider="supabase",
            supabase_service_role_key="test-service-key",
        ),
    )
    def fail_storage_cleanup(_user_id: str) -> None:
        raise MediaStorageError("storage unavailable")

    monkeypatch.setattr(routes, "delete_user_objects", fail_storage_cleanup)
    auth_deletions: list[str] = []
    monkeypatch.setattr(routes, "delete_auth_user", auth_deletions.append)

    response = client.delete("/api/account", headers={"X-User-Id": USER_ID})

    assert response.status_code == 503
    assert auth_deletions == []
    with client.app.state.testing_session_factory() as db:
        assert db.get(UserProfile, USER_ID) is not None
        assert db.get(DeletedAccount, USER_ID) is None


def test_account_deletion_can_retry_after_auth_provider_error(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.get("/api/profile", headers={"X-User-Id": USER_ID})
    monkeypatch.setattr(
        routes,
        "settings",
        SimpleNamespace(
            is_production=False,
            storage_provider="supabase",
            supabase_service_role_key="test-service-key",
        ),
    )
    monkeypatch.setattr(routes, "delete_user_objects", lambda _user_id: None)
    auth_deletions: list[str] = []

    def fail_first_auth_deletion(user_id: str) -> None:
        auth_deletions.append(user_id)
        if len(auth_deletions) == 1:
            raise MediaStorageError("authentication provider unavailable")

    monkeypatch.setattr(routes, "delete_auth_user", fail_first_auth_deletion)
    first_response = client.delete("/api/account", headers={"X-User-Id": USER_ID})
    inactive_response = client.get("/api/profile", headers={"X-User-Id": USER_ID})
    retry_response = client.delete("/api/account", headers={"X-User-Id": USER_ID})

    assert first_response.status_code == 503
    assert inactive_response.status_code == 401
    assert retry_response.status_code == 204
    assert auth_deletions == [USER_ID, USER_ID]
