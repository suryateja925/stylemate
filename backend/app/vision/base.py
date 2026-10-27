from typing import Protocol

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized coordinates, each between 0 and 1."""

    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    def valid(self) -> bool:
        return self.x_max > self.x_min and self.y_max > self.y_min


class DetectionPayload(BaseModel):
    temporary_id: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    subcategory: str | None = None
    primary_color: str | None = None
    secondary_colors: list[str] = Field(default_factory=list)
    pattern: str | None = None
    visibility_status: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox | None = None
    uncertainty_explanation: str | None = None
    requires_review: bool = True


class VisionAnalysis(BaseModel):
    detections: list[DetectionPayload] = Field(default_factory=list)
    needs_more_photos: bool = False
    summary: str | None = None


class VisionProviderError(RuntimeError):
    pass


class VisionProvider(Protocol):
    name: str

    def analyze(self, image_path: str) -> VisionAnalysis:
        ...
