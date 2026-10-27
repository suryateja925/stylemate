from pathlib import Path
from contextlib import contextmanager
import io
import tempfile
import uuid
from collections.abc import Iterator

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.config import settings
from ..storage import download_object, upload_object


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_DIMENSION = 8000
MIN_DIMENSION = 32


class ImageValidationError(ValueError):
    pass


async def read_valid_image(upload: UploadFile) -> Image.Image:
    filename = upload.filename or "image"
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ImageValidationError("Only JPG, JPEG, PNG, and WebP images are supported.")

    content = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ImageValidationError(f"Images must be {settings.max_upload_mb} MB or smaller.")
    if not content:
        raise ImageValidationError("The uploaded image is empty.")

    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("The file is not a readable image.") from exc

    width, height = image.size
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ImageValidationError(f"Images must be at least {MIN_DIMENSION}x{MIN_DIMENSION} pixels.")
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ImageValidationError(f"Images must be no larger than {MAX_DIMENSION}x{MAX_DIMENSION} pixels.")
    return image


def save_normalized_image(image: Image.Image, directory: str = "uploads", user_id: str | None = None) -> str:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    if settings.storage_provider == "supabase":
        if not user_id:
            raise ValueError("A user ID is required for private image storage.")
        relative_name = f"users/{user_id}/{directory}/{uuid.uuid4()}.jpg"
        upload_object(relative_name, output.getvalue())
        return relative_name

    relative_name = f"{directory}/{uuid.uuid4()}.jpg"
    destination = settings.media_root / relative_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output.getvalue())
    return relative_name.replace("\\", "/")


def read_image_bytes(image_path: str) -> bytes:
    if any(part in {"", ".", ".."} for part in Path(image_path).parts):
        raise ImageValidationError("Invalid image path.")
    if settings.storage_provider == "supabase":
        return download_object(image_path)
    source_path = (settings.media_root / image_path).resolve()
    if not source_path.is_relative_to(settings.media_root.resolve()):
        raise ImageValidationError("Invalid image path.")
    try:
        return source_path.read_bytes()
    except OSError as exc:
        raise ImageValidationError("The stored image could not be read.") from exc


@contextmanager
def materialize_image(image_path: str) -> Iterator[str]:
    if settings.storage_provider == "local":
        source_path = (settings.media_root / image_path).resolve()
        if not source_path.is_relative_to(settings.media_root.resolve()):
            raise ImageValidationError("Invalid image path.")
        yield str(source_path)
        return

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory) / "image.jpg"
        temporary_path.write_bytes(read_image_bytes(image_path))
        yield str(temporary_path)


def save_crop(image_path: str, bounding_box: dict[str, float], user_id: str | None = None) -> str:
    with Image.open(io.BytesIO(read_image_bytes(image_path))) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        width, height = image.size
        x_min = max(0.0, min(1.0, float(bounding_box["x_min"])))
        y_min = max(0.0, min(1.0, float(bounding_box["y_min"])))
        x_max = max(0.0, min(1.0, float(bounding_box["x_max"])))
        y_max = max(0.0, min(1.0, float(bounding_box["y_max"])))
        if x_max <= x_min or y_max <= y_min:
            raise ImageValidationError("The detection bounding box is invalid.")
        box = (int(x_min * width), int(y_min * height), int(x_max * width), int(y_max * height))
        crop = image.crop(box)
    return save_normalized_image(crop, "crops", user_id=user_id)
