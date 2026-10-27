from datetime import date, datetime, timezone
import uuid

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), default="StyleMate user")
    wardrobe_target: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    preference: Mapped["UserStylePreference | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="READY")
    original_image_path: Mapped[str] = mapped_column(String(255))
    additional_image_paths: Mapped[list] = mapped_column(JSON, default=list)
    needs_more_photos: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    detections: Mapped[list["GarmentDetection"]] = relationship(back_populates="scan", cascade="all, delete-orphan")


class GarmentDetection(Base):
    __tablename__ = "garment_detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan_sessions.id", ondelete="CASCADE"), index=True)
    temporary_id: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(80))
    subcategory: Mapped[str | None] = mapped_column(String(80), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secondary_colors: Mapped[list] = mapped_column(JSON, default=list)
    pattern: Mapped[str | None] = mapped_column(String(80), nullable=True)
    visibility_status: Mapped[str] = mapped_column(String(32), default="mostly_visible")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    bounding_box: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uncertainty_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    crop_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    scan: Mapped[ScanSession] = relationship(back_populates="detections")


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    detection_id: Mapped[str | None] = mapped_column(ForeignKey("garment_detections.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(80))
    subcategory: Mapped[str | None] = mapped_column(String(80), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secondary_colors: Mapped[list] = mapped_column(JSON, default=list)
    pattern: Mapped[str | None] = mapped_column(String(80), nullable=True)
    image_path: Mapped[str] = mapped_column(String(255))
    availability_status: Mapped[str] = mapped_column(String(24), default="available")
    laundry_status: Mapped[str] = mapped_column(String(24), default="clean")
    confirmation_status: Mapped[str] = mapped_column(String(24), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class DailyPlan(Base):
    __tablename__ = "daily_plans"
    __table_args__ = (UniqueConstraint("user_id", "plan_date", name="uq_daily_plan_user_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    events: Mapped[list["DailyPlanEvent"]] = relationship(back_populates="plan", cascade="all, delete-orphan", order_by="DailyPlanEvent.order_index")


class DailyPlanEvent(Base):
    __tablename__ = "daily_plan_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("daily_plans.id", ondelete="CASCADE"), index=True)
    event_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(100))
    occasion_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    custom_activity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setting: Mapped[str | None] = mapped_column(String(24), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dress_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    formality: Mapped[str | None] = mapped_column(String(24), nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[DailyPlan] = relationship(back_populates="events")
    preparation_tasks: Mapped[list["PreparationTask"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class PreparationTask(Base):
    __tablename__ = "preparation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("daily_plan_events.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(180))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    event: Mapped[DailyPlanEvent] = relationship(back_populates="preparation_tasks")


class AppNotification(Base):
    __tablename__ = "app_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("preparation_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="unread", index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OutfitRecommendation(Base):
    __tablename__ = "outfit_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("daily_plan_events.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=1)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text)
    limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    weather_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    items: Mapped[list["OutfitRecommendationItem"]] = relationship(back_populates="recommendation", cascade="all, delete-orphan")


class OutfitRecommendationItem(Base):
    __tablename__ = "outfit_recommendation_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("outfit_recommendations.id", ondelete="CASCADE"), index=True)
    wardrobe_item_id: Mapped[str] = mapped_column(ForeignKey("wardrobe_items.id", ondelete="CASCADE"), index=True)
    slot: Mapped[str] = mapped_column(String(32))

    recommendation: Mapped[OutfitRecommendation] = relationship(back_populates="items")


class OutfitHistory(Base):
    __tablename__ = "outfit_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("daily_plan_events.id", ondelete="SET NULL"), nullable=True)
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("outfit_recommendations.id", ondelete="SET NULL"), nullable=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24))
    outfit_signature: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserStylePreference(Base):
    __tablename__ = "user_style_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True)
    preferred_styles: Mapped[list] = mapped_column(JSON, default=list)
    favourite_colours: Mapped[list] = mapped_column(JSON, default=list)
    disliked_colours: Mapped[list] = mapped_column(JSON, default=list)
    preferred_formality: Mapped[str | None] = mapped_column(String(24), nullable=True)
    comfort_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    traditional_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_sizes: Mapped[list] = mapped_column(JSON, default=list)
    preferred_fits: Mapped[list] = mapped_column(JSON, default=list)
    shopping_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    repetition_window_days: Mapped[int] = mapped_column(Integer, default=5)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped[UserProfile] = relationship(back_populates="preference")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="StyleMate chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class VoiceCommandReceipt(Base):
    __tablename__ = "voice_command_receipts"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    utterance: Mapped[str] = mapped_column(String(1000))
    language: Mapped[str] = mapped_column(String(16), default="en")
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ShoppingSearch(Base):
    __tablename__ = "shopping_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(240))
    occasion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="links_only")
    results: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApiRateLimit(Base):
    __tablename__ = "api_rate_limits"
    __table_args__ = (UniqueConstraint("user_id", "action", name="uq_api_rate_limit_user_action"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    window_id: Mapped[int] = mapped_column(Integer)
    request_count: Mapped[int] = mapped_column(Integer)


class DeletedAccount(Base):
    __tablename__ = "deleted_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
