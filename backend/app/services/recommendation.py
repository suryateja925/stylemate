from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    DailyPlan,
    DailyPlanEvent,
    OutfitHistory,
    OutfitRecommendation,
    OutfitRecommendationItem,
    UserStylePreference,
    WardrobeItem,
)
from .weather import get_weather_provider


TOP_CATEGORIES = {"shirt", "t-shirt", "sweater", "jacket", "traditional", "blouse", "top"}
BOTTOM_CATEGORIES = {"trousers", "jeans", "shorts", "skirt", "traditional_bottom", "bottom"}
ONE_PIECE_CATEGORIES = {"dress", "jumpsuit", "traditional_dress"}
FOOTWEAR_CATEGORIES = {"footwear", "shoes", "sneakers", "sandals", "boots"}
ACCESSORY_CATEGORIES = {"accessory", "bag", "belt", "scarf", "jewellery"}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _event_key(event: DailyPlanEvent) -> str:
    return f"{_norm(event.activity_type)} {_norm(event.custom_activity)} {_norm(event.dress_code)} {_norm(event.formality)}"


def _formality(event: DailyPlanEvent) -> str:
    key = _event_key(event)
    if event.formality:
        return _norm(event.formality)
    if any(word in key for word in ("interview", "meeting", "wedding", "party", "function", "date")):
        return "formal"
    if any(word in key for word in ("gym", "sports", "home", "relaxation")):
        return "relaxed"
    return "smart_casual"


def _category_score(item: WardrobeItem, event: DailyPlanEvent) -> float:
    category = _norm(item.category)
    key = _event_key(event)
    score = 0.0
    formality = _formality(event)
    if "gym" in key or "sports" in key:
        score += 6 if category in {"t-shirt", "shorts", "sneakers", "footwear", "joggers"} else -1
    elif "wedding" in key or "traditional" in key:
        score += 7 if category in {"traditional", "traditional_dress", "dress", "jacket", "footwear", "shoes"} else 0
    elif formality == "formal":
        score += 5 if category in {"shirt", "blouse", "trousers", "dress", "skirt", "jacket", "footwear", "shoes"} else -1
    elif formality == "relaxed":
        score += 3 if category in {"t-shirt", "jeans", "shorts", "sweater", "sneakers", "footwear"} else 0
    else:
        score += 2 if category in TOP_CATEGORIES | BOTTOM_CATEGORIES | ONE_PIECE_CATEGORIES else 0
    return score


def _colour_score(item: WardrobeItem, preference: UserStylePreference | None) -> float:
    if not preference:
        return 0
    colour = _norm(item.primary_color)
    score = 0.0
    if colour in {_norm(value) for value in (preference.favourite_colours or [])}:
        score += 3
    if colour in {_norm(value) for value in (preference.disliked_colours or [])}:
        score -= 8
    return score


def _recent_signatures(db: Session, user_id: str, plan_date: date, window_days: int) -> set[tuple[str, ...]]:
    start = plan_date - timedelta(days=window_days)
    rows = db.scalars(
        select(OutfitHistory).where(
            OutfitHistory.user_id == user_id,
            OutfitHistory.status == "worn",
            OutfitHistory.plan_date >= start,
            OutfitHistory.plan_date < plan_date,
        )
    ).all()
    return {tuple(sorted(row.outfit_signature or [])) for row in rows}


def _build_combinations(items: list[WardrobeItem], event: DailyPlanEvent, preference: UserStylePreference | None) -> list[tuple[list[tuple[str, WardrobeItem]], float]]:
    tops = [item for item in items if _norm(item.category) in TOP_CATEGORIES]
    bottoms = [item for item in items if _norm(item.category) in BOTTOM_CATEGORIES]
    one_piece = [item for item in items if _norm(item.category) in ONE_PIECE_CATEGORIES]
    footwear = [item for item in items if _norm(item.category) in FOOTWEAR_CATEGORIES]
    accessories = [item for item in items if _norm(item.category) in ACCESSORY_CATEGORIES]
    key = _event_key(event)
    candidates: list[tuple[list[tuple[str, WardrobeItem]], float]] = []

    for item in one_piece:
        score = 10 + _category_score(item, event) + _colour_score(item, preference)
        candidates.append(([("one_piece", item)], score))
    for top in tops:
        for bottom in bottoms:
            score = 12 + _category_score(top, event) + _category_score(bottom, event)
            score += _colour_score(top, preference) + _colour_score(bottom, preference)
            if _norm(top.primary_color) == _norm(bottom.primary_color) and _norm(top.primary_color):
                score -= 1
            if footwear:
                shoe = max(footwear, key=lambda item: _category_score(item, event) + _colour_score(item, preference))
                candidates.append(([("top", top), ("bottom", bottom), ("footwear", shoe)], score + _category_score(shoe, event)))
            else:
                candidates.append(([("top", top), ("bottom", bottom)], score))

    # If a user has only one useful real item, still explain the limitation.
    if not candidates:
        for item in items:
            candidates.append(([("piece", item)], _category_score(item, event) + _colour_score(item, preference)))

    for candidate, score in candidates:
        if accessories:
            accessory = max(accessories, key=lambda item: _category_score(item, event) + _colour_score(item, preference))
            if "party" in key or "date" in key or "wedding" in key:
                candidate.append(("accessory", accessory))
                score += 1
    return candidates


def generate_for_event(db: Session, user_id: str, plan: DailyPlan, event: DailyPlanEvent, replace: bool = False) -> list[OutfitRecommendation]:
    preference = db.scalar(select(UserStylePreference).where(UserStylePreference.user_id == user_id))
    items = db.scalars(
        select(WardrobeItem).where(
            WardrobeItem.user_id == user_id,
            WardrobeItem.confirmation_status == "confirmed",
            WardrobeItem.availability_status == "available",
            WardrobeItem.laundry_status != "in_laundry",
        )
    ).all()
    recent = _recent_signatures(db, user_id, plan.plan_date, preference.repetition_window_days if preference else 5)
    candidates = _build_combinations(items, event, preference)
    candidates.sort(key=lambda pair: pair[1], reverse=True)

    existing = db.scalars(select(OutfitRecommendation).where(OutfitRecommendation.event_id == event.id, OutfitRecommendation.is_current.is_(True))).all()
    for row in existing:
        row.is_current = False

    recommendations: list[OutfitRecommendation] = []
    for rank, (selected, raw_score) in enumerate(candidates[:3], start=1):
        ids = tuple(sorted(item.id for _, item in selected))
        repeated = ids in recent
        score = raw_score - (10 if repeated else 0)
        labels = ", ".join(item.primary_color or item.category for _, item in selected)
        reason = f"Uses {labels} from your confirmed wardrobe and matches the {_formality(event).replace('_', ' ')} tone of this event."
        limitation = None
        if len(selected) == 1:
            limitation = "Your available wardrobe does not currently contain a complete combination for this event, so this is the closest available piece."
        if repeated:
            reason += " It is lower-ranked because this combination was worn recently."
        weather = get_weather_provider().forecast(event.location, event.start_time)
        recommendation = OutfitRecommendation(
            user_id=user_id,
            event_id=event.id,
            rank=rank,
            score=score,
            reason=reason,
            limitation=limitation,
            weather_note=weather.summary if weather else None,
            is_current=(rank == 1),
        )
        db.add(recommendation)
        db.flush()
        for slot, item in selected:
            db.add(OutfitRecommendationItem(recommendation_id=recommendation.id, wardrobe_item_id=item.id, slot=slot))
        recommendations.append(recommendation)

    if not candidates:
        recommendation = OutfitRecommendation(
            user_id=user_id,
            event_id=event.id,
            rank=1,
            score=0,
            reason="No available confirmed wardrobe items match this event yet.",
            limitation="Add and confirm more wardrobe items, or mark clean items as available.",
            is_current=True,
        )
        db.add(recommendation)
        db.flush()
        recommendations.append(recommendation)
    db.commit()
    for recommendation in recommendations:
        db.refresh(recommendation)
    return recommendations


def recommendation_with_items(db: Session, recommendation_id: str, user_id: str) -> OutfitRecommendation | None:
    return db.scalar(
        select(OutfitRecommendation)
        .options(selectinload(OutfitRecommendation.items))
        .where(OutfitRecommendation.id == recommendation_id, OutfitRecommendation.user_id == user_id)
    )
