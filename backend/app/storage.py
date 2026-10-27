import re
from urllib.parse import quote, urlparse

import httpx

from .core.config import settings


class MediaStorageError(RuntimeError):
    pass


def _headers(content_type: str = "application/json") -> dict[str, str]:
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Content-Type": content_type,
    }
    if not settings.supabase_service_role_key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {settings.supabase_service_role_key}"
    return headers


def _object_url(path: str) -> str:
    bucket = quote(settings.supabase_storage_bucket, safe="")
    object_path = quote(path, safe="/")
    return f"{settings.supabase_url}/storage/v1/object/{bucket}/{object_path}"


def upload_object(path: str, content: bytes) -> None:
    try:
        response = httpx.post(
            _object_url(path),
            content=content,
            headers={**_headers("image/jpeg"), "x-upsert": "false"},
            timeout=settings.ai_request_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MediaStorageError("Image storage is temporarily unavailable.") from exc
    if response.is_error:
        raise MediaStorageError(f"Image storage rejected an upload (HTTP {response.status_code}).")


def download_object(path: str) -> bytes:
    try:
        response = httpx.get(
            _object_url(path),
            headers=_headers(),
            timeout=settings.ai_request_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MediaStorageError("Image storage is temporarily unavailable.") from exc
    if response.is_error:
        raise MediaStorageError(f"Image storage could not retrieve an image (HTTP {response.status_code}).")
    return response.content


def create_signed_url(path: str) -> str:
    bucket = quote(settings.supabase_storage_bucket, safe="")
    encoded_path = quote(path, safe="/")
    try:
        response = httpx.post(
            f"{settings.supabase_url}/storage/v1/object/sign/{bucket}/{encoded_path}",
            headers=_headers(),
            json={"expiresIn": 3600},
            timeout=settings.ai_request_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MediaStorageError("Image storage is temporarily unavailable.") from exc
    if response.is_error:
        raise MediaStorageError(f"Image storage could not create a private image link (HTTP {response.status_code}).")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MediaStorageError("Image storage returned an invalid private image link.") from exc
    signed_path = payload.get("signedURL") if isinstance(payload, dict) else None
    if not isinstance(signed_path, str) or not signed_path:
        raise MediaStorageError("Image storage returned an invalid private image link.")
    if signed_path.startswith("http://") or signed_path.startswith("https://"):
        parsed_signed_path = urlparse(signed_path)
        if parsed_signed_path.scheme != "https" or parsed_signed_path.netloc != urlparse(settings.supabase_url).netloc:
            raise MediaStorageError("Image storage returned an untrusted private image link.")
        return signed_path
    return f"{settings.supabase_url}/storage/v1/{signed_path.lstrip('/')}"


def delete_user_objects(user_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
        raise MediaStorageError("The user ID is invalid for private image storage.")
    bucket = quote(settings.supabase_storage_bucket, safe="")
    root = f"users/{user_id}"
    object_paths: list[str] = []

    def list_folder(prefix: str) -> None:
        offset = 0
        while True:
            try:
                response = httpx.post(
                    f"{settings.supabase_url}/storage/v1/object/list/{bucket}",
                    headers=_headers(),
                    json={"prefix": prefix, "limit": 100, "offset": offset},
                    timeout=settings.ai_request_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise MediaStorageError("Image storage is temporarily unavailable.") from exc
            if response.is_error:
                raise MediaStorageError(f"Image storage could not list account images (HTTP {response.status_code}).")
            try:
                entries = response.json()
            except ValueError as exc:
                raise MediaStorageError("Image storage returned an invalid object listing.") from exc
            if not isinstance(entries, list):
                raise MediaStorageError("Image storage returned an invalid object listing.")
            for entry in entries:
                name = entry.get("name") if isinstance(entry, dict) else None
                if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name:
                    raise MediaStorageError("Image storage returned an invalid object path.")
                path = f"{prefix}/{name}"
                if entry.get("id") is None:
                    list_folder(path)
                else:
                    object_paths.append(path)
            if len(entries) < 100:
                return
            offset += len(entries)

    list_folder(root)
    for start in range(0, len(object_paths), 100):
        try:
            response = httpx.post(
                f"{settings.supabase_url}/storage/v1/object/{bucket}",
                headers=_headers(),
                json={"prefixes": object_paths[start : start + 100]},
                timeout=settings.ai_request_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise MediaStorageError("Image storage is temporarily unavailable.") from exc
        if response.is_error:
            raise MediaStorageError(f"Image storage could not delete account images (HTTP {response.status_code}).")


def delete_auth_user(user_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
        raise MediaStorageError("The user ID is invalid for account deletion.")
    try:
        response = httpx.delete(
            f"{settings.supabase_url}/auth/v1/admin/users/{quote(user_id, safe='')}",
            headers=_headers(),
            timeout=settings.ai_request_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MediaStorageError("The authentication provider is temporarily unavailable.") from exc
    if response.is_error:
        raise MediaStorageError(f"The authentication provider could not delete the account (HTTP {response.status_code}).")
