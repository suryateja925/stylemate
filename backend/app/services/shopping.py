from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ShoppingSearch, UserStylePreference, WardrobeItem
from ..schemas import ShoppingSearchIn
from ..shopping.base import PROVIDERS, ShoppingLink


def wardrobe_context(db: Session, user_id: str) -> list[str]:
    items = db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == user_id, WardrobeItem.confirmation_status == "confirmed")).all()
    return [f"{item.primary_color or 'unknown colour'} {item.category}" for item in items]


def infer_missing_piece(context: list[str], occasion: str | None) -> str:
    categories = {line.rsplit(" ", 1)[-1].lower() for line in context}
    occasion_text = (occasion or "everyday outfit").lower()
    if "wedding" in occasion_text or "traditional" in occasion_text:
        return "traditional outfit"
    if not any(category in categories for category in ("shirt", "t-shirt", "top", "dress", "traditional")):
        return "versatile shirt"
    if not any(category in categories for category in ("trousers", "jeans", "skirt", "shorts", "bottom")):
        return "neutral trousers"
    if not any(category in categories for category in ("footwear", "shoes", "sneakers", "sandals", "boots")):
        return "comfortable footwear"
    return "wardrobe complement"


def build_query(payload: ShoppingSearchIn, context: list[str]) -> str:
    base = payload.query or infer_missing_piece(context, payload.occasion)
    parts = [base]
    if payload.occasion:
        parts.append(payload.occasion)
    if payload.colour:
        parts.append(payload.colour)
    if payload.style:
        parts.append(payload.style)
    if payload.size:
        parts.append(payload.size)
    if payload.budget is not None:
        parts.append(f"under INR {payload.budget:g}")
    return " ".join(parts)


def create_search(db: Session, user_id: str, payload: ShoppingSearchIn) -> tuple[ShoppingSearch, list[str], list[ShoppingLink]]:
    context = wardrobe_context(db, user_id) if payload.use_wardrobe_first else []
    query = build_query(payload, context)
    provider_names = payload.providers or list(PROVIDERS)
    links = [PROVIDERS[name].search_link(query) for name in provider_names if name in PROVIDERS]
    search = ShoppingSearch(user_id=user_id, query=query, occasion=payload.occasion, budget=payload.budget, results=[link.__dict__ for link in links])
    db.add(search)
    db.commit()
    db.refresh(search)
    return search, context, links
