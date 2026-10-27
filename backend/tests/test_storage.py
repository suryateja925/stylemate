from types import SimpleNamespace

import pytest

from backend.app import storage
from backend.app.storage import MediaStorageError


def test_secret_api_key_is_sent_without_a_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "settings", SimpleNamespace(supabase_service_role_key="sb_secret_test"))
    headers = storage._headers()

    assert headers["apikey"] == "sb_secret_test"
    assert "Authorization" not in headers


def test_legacy_service_role_key_is_sent_as_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "settings", SimpleNamespace(supabase_service_role_key="legacy-service-role-jwt"))
    headers = storage._headers()

    assert headers["apikey"] == "legacy-service-role-jwt"
    assert headers["Authorization"] == "Bearer legacy-service-role-jwt"


class StorageResponse:
    is_error = False
    status_code = 200

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def json(self) -> object:
        return self.payload


def test_signed_media_urls_are_limited_to_the_configured_https_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        storage,
        "settings",
        SimpleNamespace(
            supabase_url="https://project.supabase.co",
            supabase_service_role_key="server-test-key",
            supabase_storage_bucket="wardrobe-private",
            ai_request_timeout_seconds=5,
        ),
    )
    monkeypatch.setattr(
        storage.httpx,
        "post",
        lambda *_args, **_kwargs: StorageResponse({"signedURL": "/object/sign/wardrobe-private/users/user/image.jpg?token=test"}),
    )

    result = storage.create_signed_url("users/user/image.jpg")

    assert result == "https://project.supabase.co/storage/v1/object/sign/wardrobe-private/users/user/image.jpg?token=test"


def test_signed_media_url_rejects_an_untrusted_storage_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        storage,
        "settings",
        SimpleNamespace(
            supabase_url="https://project.supabase.co",
            supabase_service_role_key="server-test-key",
            supabase_storage_bucket="wardrobe-private",
            ai_request_timeout_seconds=5,
        ),
    )
    monkeypatch.setattr(
        storage.httpx,
        "post",
        lambda *_args, **_kwargs: StorageResponse({"signedURL": "https://attacker.example/file"}),
    )

    with pytest.raises(MediaStorageError, match="untrusted"):
        storage.create_signed_url("users/user/image.jpg")


def test_account_media_deletion_lists_nested_objects_and_deletes_exact_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        storage,
        "settings",
        SimpleNamespace(
            supabase_url="https://project.supabase.co",
            supabase_service_role_key="server-test-key",
            supabase_storage_bucket="wardrobe-private",
            ai_request_timeout_seconds=5,
        ),
    )
    responses = iter([
        StorageResponse([{"name": "uploads", "id": None}]),
        StorageResponse([{"name": "photo.jpg", "id": "object-id"}]),
        StorageResponse({}),
    ])
    requests: list[tuple[str, dict[str, object]]] = []

    def mock_post(url: str, **kwargs: object) -> StorageResponse:
        requests.append((url, kwargs))
        return next(responses)

    monkeypatch.setattr(storage.httpx, "post", mock_post)

    storage.delete_user_objects("user-id")

    assert [url.rsplit("/", 1)[-1] for url, _ in requests] == ["wardrobe-private", "wardrobe-private", "wardrobe-private"]
    assert requests[0][1]["json"] == {"prefix": "users/user-id", "limit": 100, "offset": 0}
    assert requests[1][1]["json"] == {"prefix": "users/user-id/uploads", "limit": 100, "offset": 0}
    assert requests[2][1]["json"] == {"prefixes": ["users/user-id/uploads/photo.jpg"]}
