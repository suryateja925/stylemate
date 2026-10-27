from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Conversation, ConversationMessage, DailyPlan, UserStylePreference, WardrobeItem
from ..conversation.factory import get_text_provider


def context_for_user(db: Session, user_id: str) -> str:
    wardrobe = db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == user_id, WardrobeItem.confirmation_status == "confirmed")).all()
    preference = db.scalar(select(UserStylePreference).where(UserStylePreference.user_id == user_id))
    plans = db.scalars(select(DailyPlan).where(DailyPlan.user_id == user_id).order_by(DailyPlan.plan_date.desc()).limit(3)).all()
    wardrobe_lines = [f"- id={item.id}; category={item.category}; colour={item.primary_color or 'unknown'}; pattern={item.pattern or 'unknown'}; availability={item.availability_status}; laundry={item.laundry_status}" for item in wardrobe]
    preference_line = f"styles={preference.preferred_styles}; favourite_colours={preference.favourite_colours}; disliked_colours={preference.disliked_colours}; sizes={preference.preferred_sizes}; fits={preference.preferred_fits}" if preference else "No explicit style preferences saved."
    plan_lines = [f"- date={plan.plan_date}; events={len(plan.events)}" for plan in plans]
    return "Confirmed wardrobe:\n" + ("\n".join(wardrobe_lines) or "(empty)") + f"\nPreferences: {preference_line}\nRecent plans:\n" + ("\n".join(plan_lines) or "(none)")


def conversation_messages(db: Session, conversation_id: str, user_id: str) -> list[ConversationMessage]:
    conversation = db.scalar(select(Conversation).options(selectinload(Conversation.messages)).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
    return list(conversation.messages) if conversation else []


def provider_status() -> dict[str, str | bool]:
    try:
        provider = get_text_provider()
        return {"configured": True, "provider": provider.name}
    except Exception:
        return {"configured": False, "provider": "none"}
