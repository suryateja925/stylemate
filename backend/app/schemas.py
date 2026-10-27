from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfileOut(ApiModel):
    id: str
    display_name: str
    wardrobe_target: int


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    wardrobe_target: int | None = Field(default=None, ge=1, le=10000)


class DetectionOut(ApiModel):
    id: str
    temporary_id: str
    category: str
    subcategory: str | None
    primary_color: str | None
    secondary_colors: list[str]
    pattern: str | None
    visibility_status: str
    confidence: float
    bounding_box: dict[str, float] | None
    uncertainty_explanation: str | None
    requires_review: bool
    crop_path: str | None
    confirmed: bool
    rejected: bool
    image_url: str | None = None


class ScanOut(ApiModel):
    id: str
    status: str
    original_image_path: str
    original_image_url: str
    additional_image_paths: list[str]
    needs_more_photos: bool
    error_message: str | None
    detections: list[DetectionOut]


class DetectionPatch(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    subcategory: str | None = Field(default=None, max_length=80)
    primary_color: str | None = Field(default=None, max_length=80)
    secondary_colors: list[str] | None = None
    pattern: str | None = Field(default=None, max_length=80)
    rejected: bool | None = None


class ConfirmRequest(BaseModel):
    detection_ids: list[str] = Field(min_length=1)


class WardrobePatch(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    subcategory: str | None = Field(default=None, max_length=80)
    primary_color: str | None = Field(default=None, max_length=80)
    secondary_colors: list[str] | None = None
    pattern: str | None = Field(default=None, max_length=80)
    availability_status: Literal["available", "unavailable"] | None = None
    laundry_status: Literal["clean", "in_laundry"] | None = None


class WardrobeOut(ApiModel):
    id: str
    category: str
    subcategory: str | None
    primary_color: str | None
    secondary_colors: list[str]
    pattern: str | None
    image_path: str
    image_url: str
    availability_status: str
    laundry_status: str
    confirmation_status: str
    created_at: datetime


class PlanEventIn(BaseModel):
    event_name: str | None = Field(default=None, max_length=160)
    activity_type: str = Field(min_length=1, max_length=100)
    occasion_type: str | None = Field(default=None, max_length=100)
    custom_activity: str | None = Field(default=None, max_length=120)
    start_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    setting: Literal["indoor", "outdoor", "both"] | None = None
    location: str | None = Field(default=None, max_length=160)
    dress_code: str | None = Field(default=None, max_length=80)
    formality: Literal["relaxed", "smart_casual", "formal", "traditional"] | None = None
    budget: float | None = Field(default=None, ge=0, le=10_000_000)
    preferences: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("start_time")
    @classmethod
    def valid_time(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("start_time must use HH:MM")
        hour, minute = (int(part) for part in parts)
        if hour > 23 or minute > 59:
            raise ValueError("start_time must use a valid 24-hour time")
        return value


class PlanCreate(BaseModel):
    plan_date: date
    events: list[PlanEventIn] = Field(min_length=1, max_length=20)


class PlanEventOut(ApiModel):
    id: str
    event_name: str | None
    activity_type: str
    occasion_type: str | None
    custom_activity: str | None
    start_time: str | None
    duration_minutes: int | None
    setting: str | None
    location: str | None
    dress_code: str | None
    formality: str | None
    budget: float | None
    preferences: str | None
    notes: str | None
    cancelled: bool
    order_index: int


class PlanOut(ApiModel):
    id: str
    plan_date: date
    status: str
    saved_at: datetime | None
    events: list[PlanEventOut]


class PreferenceIn(BaseModel):
    preferred_styles: list[str] | None = None
    favourite_colours: list[str] | None = None
    disliked_colours: list[str] | None = None
    preferred_formality: Literal["relaxed", "smart_casual", "formal", "traditional"] | None = None
    comfort_preferences: str | None = Field(default=None, max_length=500)
    traditional_preferences: str | None = Field(default=None, max_length=500)
    preferred_sizes: list[str] | None = None
    preferred_fits: list[str] | None = None
    shopping_budget: float | None = Field(default=None, ge=0, le=10_000_000)
    repetition_window_days: int | None = Field(default=None, ge=0, le=60)
    reminders_enabled: bool | None = None
    reminder_time: str | None = None


class PreferenceOut(ApiModel):
    preferred_styles: list[str]
    favourite_colours: list[str]
    disliked_colours: list[str]
    preferred_formality: str | None
    comfort_preferences: str | None
    traditional_preferences: str | None
    preferred_sizes: list[str]
    preferred_fits: list[str]
    shopping_budget: float | None
    repetition_window_days: int
    reminders_enabled: bool
    reminder_time: str | None


class RecommendationGenerateIn(BaseModel):
    plan_id: str
    event_id: str | None = None


class RecommendationItemOut(BaseModel):
    wardrobe_item_id: str
    slot: str
    wardrobe_item: WardrobeOut


class RecommendationOut(ApiModel):
    id: str
    event_id: str
    rank: int
    score: float
    reason: str
    limitation: str | None
    weather_note: str | None
    status: str
    is_current: bool
    items: list[RecommendationItemOut]


class EventRecommendationsOut(BaseModel):
    event: PlanEventOut
    recommendations: list[RecommendationOut]


class ProgressOut(BaseModel):
    confirmed_wardrobe_items: int
    bundle_scans: int
    successful_scans: int
    failed_scans: int
    awaiting_review: int
    generated_outfits: int
    saved_outfits: int
    worn_outfits: int
    weekly_activity: list[dict[str, Any]]
    category_coverage: list[dict[str, Any]]
    wardrobe_target: int
    completion_percentage: float
    upcoming_events: int = 0
    completed_preparation_tasks: int = 0
    pending_preparation_tasks: int = 0


class PreparationTaskOut(ApiModel):
    id: str
    event_id: str
    task_type: str
    title: str
    due_at: datetime
    status: str
    snoozed_until: datetime | None
    completed_at: datetime | None


class TaskSnoozeIn(BaseModel):
    until: datetime


class NotificationOut(ApiModel):
    id: str
    title: str
    message: str
    status: str
    scheduled_for: datetime
    created_at: datetime


class ChatMessageIn(BaseModel):
    conversation_id: str | None = None
    content: str = Field(min_length=1, max_length=4000)
    language: Literal["en", "te", "mixed"] | None = None


class ChatMessageOut(ApiModel):
    id: str
    role: str
    content: str
    language: str | None
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: str
    provider: str
    configured: bool
    message: ChatMessageOut
    follow_up_questions: list[str] = []


class VoiceCommandIn(BaseModel):
    request_id: str = Field(min_length=36, max_length=36)
    utterance: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "te", "mixed"] = "en"


class VoiceCommandOut(BaseModel):
    request_id: str
    action: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    navigate_to: str | None = None
    warning: str | None = None


class ShoppingSearchIn(BaseModel):
    query: str | None = Field(default=None, max_length=240)
    occasion: str | None = Field(default=None, max_length=120)
    budget: float | None = Field(default=None, ge=0, le=10_000_000)
    size: str | None = Field(default=None, max_length=40)
    colour: str | None = Field(default=None, max_length=80)
    style: str | None = Field(default=None, max_length=80)
    use_wardrobe_first: bool = True
    providers: list[Literal["amazon", "flipkart", "meesho"]] | None = None


class ShoppingResult(BaseModel):
    provider: str
    url: str
    query: str
    live_catalog: bool
    price: float | None = None
    delivery_estimate: str | None = None
    source_last_updated: datetime | None = None
    disclosure: str


class ShoppingSearchOut(BaseModel):
    id: str
    query: str
    wardrobe_context: list[str]
    budget: float | None
    status: str
    results: list[ShoppingResult]
    created_at: datetime
