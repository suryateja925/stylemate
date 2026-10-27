from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..conversation.base import ConversationProviderError
from ..conversation.factory import get_text_provider
from ..models import (
    AppNotification,
    DailyPlan,
    DailyPlanEvent,
    OutfitHistory,
    OutfitRecommendation,
    PreparationTask,
    UserStylePreference,
    VoiceCommandReceipt,
    WardrobeItem,
    utc_now,
)
from ..schemas import PlanEventIn, PreferenceIn, ShoppingSearchIn
from ..services.conversation import context_for_user
from ..services.recommendation import generate_for_event, recommendation_with_items
from ..services.shopping import create_search


VOICE_TOOLS = {
    "wardrobe_search",
    "schedule_lookup",
    "create_event",
    "edit_event",
    "recommend_outfit",
    "shopping_search",
    "preparation_tasks",
    "complete_preparation_task",
    "preferences_lookup",
    "update_preferences",
    "outfit_history",
    "reminder_lookup",
    "open_scanner",
    "save_outfit",
    "accept_current_outfit",
    "reject_current_outfit",
    "chat",
}


def _as_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def execute_voice_tool(db: Session, user_id: str, utterance: str) -> dict[str, Any]:
    provider = get_text_provider()
    context = f"Today is {date.today().isoformat()}.\n{context_for_user(db, user_id)}"
    recent = db.scalars(
        select(VoiceCommandReceipt)
        .where(VoiceCommandReceipt.user_id == user_id, VoiceCommandReceipt.created_at >= utc_now() - timedelta(minutes=30))
        .order_by(VoiceCommandReceipt.created_at.desc())
        .limit(6)
    ).all()
    if recent:
        lines = [f"User: {entry.utterance}\nAssistant: {entry.response.get('message', '')}" for entry in reversed(recent)]
        context += "\nRecent voice conversation:\n" + "\n".join(lines)
    decision = provider.select_tool(utterance, context)
    tool = decision.get("tool")
    arguments = decision.get("arguments", {})
    if not isinstance(tool, str) or tool not in VOICE_TOOLS or not isinstance(arguments, dict):
        raise ConversationProviderError("The AI returned an unsupported voice action.")

    if tool == "chat":
        answer = provider.reply(
            [{"role": "user", "content": utterance}],
            context + "\nAsk one brief clarifying question if required. Be concise and respond in the user's language.",
        )
        return {"action": "chat", "message": answer, "data": {}}

    if tool == "wardrobe_search":
        query = select(WardrobeItem).where(
            WardrobeItem.user_id == user_id,
            WardrobeItem.confirmation_status == "confirmed",
        )
        colour = arguments.get("colour")
        category = arguments.get("category")
        if isinstance(colour, str) and colour.strip():
            query = query.where(WardrobeItem.primary_color.ilike(f"%{colour.strip()[:80]}%"))
        if isinstance(category, str) and category.strip():
            query = query.where(WardrobeItem.category.ilike(f"%{category.strip()[:80]}%"))
        items = db.scalars(query.order_by(WardrobeItem.created_at.desc()).limit(20)).all()
        labels = [f"{item.primary_color or 'Unspecified colour'} {item.category}" for item in items]
        message = f"I found {len(items)} confirmed wardrobe item(s): {', '.join(labels)}." if items else "I couldn't find matching confirmed items in your wardrobe."
        return {"action": tool, "message": message, "data": {"items": [{"id": item.id, "category": item.category, "colour": item.primary_color, "subcategory": item.subcategory, "availability": item.availability_status, "laundry": item.laundry_status} for item in items]}}

    if tool == "schedule_lookup":
        start = _as_date(arguments.get("start_date")) or date.today()
        end = _as_date(arguments.get("end_date")) or start
        if end < start:
            end = start
        plans = db.scalars(
            select(DailyPlan)
            .options(selectinload(DailyPlan.events))
            .where(DailyPlan.user_id == user_id, DailyPlan.plan_date >= start, DailyPlan.plan_date <= end)
            .order_by(DailyPlan.plan_date)
        ).all()
        events = [{"date": plan.plan_date.isoformat(), "activity": event.custom_activity or event.activity_type, "time": event.start_time} for plan in plans for event in plan.events if not event.cancelled]
        message = f"You have {len(events)} event(s) from {start.isoformat()} through {end.isoformat()}." if events else f"You have no saved events from {start.isoformat()} through {end.isoformat()}."
        return {"action": tool, "message": message, "data": {"events": events}}

    if tool == "create_event":
        event_date = _as_date(arguments.get("event_date"))
        activity = arguments.get("activity")
        if not event_date or not isinstance(activity, str) or not activity.strip():
            missing = "What date should I add the event for?" if not event_date else "What event should I add?"
            return {"action": "clarification", "message": missing, "data": {}}
        start_time = arguments.get("start_time")
        formality = arguments.get("formality")
        event_data: dict[str, Any] = {"activity_type": activity.strip()[:100], "custom_activity": activity.strip()[:120]}
        if isinstance(start_time, str):
            event_data["start_time"] = start_time
        if formality in {"relaxed", "smart_casual", "formal", "traditional"}:
            event_data["formality"] = formality
        try:
            event_payload = PlanEventIn(**event_data)
        except ValidationError:
            return {"action": "clarification", "message": "What valid start time should I use? Please say it like 09:30, or omit the time.", "data": {}}
        from ..api.routes import append_plan_event

        plan = append_plan_event(db, user_id, event_date, event_payload)
        return {"action": tool, "message": f"Added {activity.strip()} to your plan for {plan.plan_date.isoformat()}.", "data": {"plan_id": plan.id, "date": plan.plan_date.isoformat(), "events": [event.custom_activity or event.activity_type for event in plan.events]}}

    if tool == "edit_event":
        event_date = _as_date(arguments.get("event_date"))
        activity = arguments.get("activity")
        if not event_date or not isinstance(activity, str) or not activity.strip():
            return {"action": "clarification", "message": "Which event and date should I update?", "data": {}}
        plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.user_id == user_id, DailyPlan.plan_date == event_date))
        matching = [event for event in (plan.events if plan else []) if activity.casefold() in (event.custom_activity or event.activity_type).casefold()]
        if len(matching) != 1:
            prompt = "I couldn't find that event." if not matching else "I found more than one matching event. Please give me its exact name."
            return {"action": "clarification", "message": prompt, "data": {}}
        event = matching[0]
        new_activity = arguments.get("new_activity")
        start_time = arguments.get("start_time")
        formality = arguments.get("formality")
        validated_start_time: str | None = None
        if isinstance(start_time, str):
            try:
                validated_start_time = PlanEventIn(activity_type=event.activity_type, start_time=start_time).start_time
            except ValidationError:
                return {"action": "clarification", "message": "What valid start time should I use? Please say it like 09:30, or omit the time.", "data": {}}
        if isinstance(new_activity, str) and new_activity.strip():
            event.custom_activity = new_activity.strip()[:120]
            event.activity_type = new_activity.strip()[:100]
        if validated_start_time is not None:
            event.start_time = validated_start_time
        if formality in {"relaxed", "smart_casual", "formal", "traditional"}:
            event.formality = formality
        db.commit()
        return {"action": tool, "message": f"Updated {event.custom_activity or event.activity_type} on {event_date.isoformat()}.", "data": {"event_id": event.id, "date": event_date.isoformat()}}

    if tool == "recommend_outfit":
        plan_date = _as_date(arguments.get("event_date"))
        if not plan_date:
            return {"action": "clarification", "message": "Which date should I plan an outfit for?", "data": {}}
        plan = db.scalar(
            select(DailyPlan)
            .options(selectinload(DailyPlan.events))
            .where(DailyPlan.user_id == user_id, DailyPlan.plan_date == plan_date)
        )
        if not plan or not plan.events:
            return {"action": "clarification", "message": f"I couldn't find an event on {plan_date.isoformat()}. Tell me the event and I can add it first.", "data": {}}
        output = []
        for event in plan.events:
            recommendations = generate_for_event(db, user_id, plan, event)
            current = next((item for item in recommendations if item.is_current), recommendations[0] if recommendations else None)
            if current:
                loaded = recommendation_with_items(db, current.id, user_id)
                if loaded:
                    pieces = [f"{item.wardrobe_item.primary_color or ''} {item.wardrobe_item.category}".strip() for item in loaded.items]
                    output.append({"event": event.custom_activity or event.activity_type, "recommendation_id": loaded.id, "items": pieces, "reason": loaded.reason})
        if not output or not any(entry["items"] for entry in output):
            return {"action": tool, "message": "I couldn't generate an outfit because no suitable confirmed wardrobe items are available.", "data": {"recommendations": output, "navigate_to": "/recommendations"}}
        description = "; ".join(f"{entry['event']}: {', '.join(entry['items'])}" for entry in output)
        return {"action": tool, "message": f"Outfit suggestions for {plan_date.isoformat()}: {description}.", "data": {"recommendations": output, "navigate_to": "/recommendations"}}

    if tool == "shopping_search":
        query = arguments.get("query")
        occasion = arguments.get("occasion")
        budget = arguments.get("budget")
        search_payload = ShoppingSearchIn(
            query=query[:240] if isinstance(query, str) else None,
            occasion=occasion[:120] if isinstance(occasion, str) else None,
            budget=budget if isinstance(budget, (int, float)) and not isinstance(budget, bool) else None,
            use_wardrobe_first=True,
        )
        search, _, links = create_search(db, user_id, search_payload)
        data = {"search_id": search.id, "query": search.query, "results": [{"provider": link.provider, "url": link.url, "disclosure": link.disclosure} for link in links]}
        return {"action": tool, "message": f"I prepared {len(links)} shopping search link(s) for {search.query}. These are search links, not live stock or price quotes.", "data": data}

    if tool == "preparation_tasks":
        target_date = _as_date(arguments.get("event_date"))
        query = select(PreparationTask).where(PreparationTask.user_id == user_id, PreparationTask.status != "completed")
        if target_date:
            due_through = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
            query = query.where(PreparationTask.due_at <= due_through)
        tasks = db.scalars(query.order_by(PreparationTask.due_at).limit(20)).all()
        data = [{"id": task.id, "title": task.title, "status": task.status, "due_at": task.due_at.isoformat()} for task in tasks]
        message = f"You have {len(tasks)} pending preparation task(s)." if tasks else "You have no pending preparation tasks."
        return {"action": tool, "message": message, "data": {"tasks": data}}

    if tool == "complete_preparation_task":
        title = arguments.get("task_title")
        if not isinstance(title, str) or not title.strip():
            return {"action": "clarification", "message": "Which preparation task did you complete?", "data": {}}
        tasks = db.scalars(select(PreparationTask).where(PreparationTask.user_id == user_id, PreparationTask.status != "completed")).all()
        matching = [task for task in tasks if title.casefold() in task.title.casefold()]
        if len(matching) != 1:
            return {"action": "clarification", "message": "I couldn't identify one unique pending task. Please say more of its title.", "data": {}}
        task = matching[0]
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"action": tool, "message": f"Marked “{task.title}” complete.", "data": {"task_id": task.id, "status": task.status}}

    if tool == "preferences_lookup":
        preference = db.get(UserStylePreference, user_id)
        if not preference:
            return {"action": tool, "message": "You haven't saved style preferences yet.", "data": {}}
        data = {"preferred_styles": preference.preferred_styles or [], "favourite_colours": preference.favourite_colours or [], "disliked_colours": preference.disliked_colours or [], "preferred_formality": preference.preferred_formality}
        return {"action": tool, "message": f"Your saved style preferences are {', '.join(data['preferred_styles']) or 'not specified'}; favourite colours are {', '.join(data['favourite_colours']) or 'not specified'}.", "data": data}

    if tool == "outfit_history":
        rows = db.scalars(select(OutfitHistory).where(OutfitHistory.user_id == user_id).order_by(OutfitHistory.created_at.desc()).limit(10)).all()
        entries = [{"date": row.plan_date.isoformat(), "event": row.event_type, "status": row.status} for row in rows]
        message = f"Your recent outfit history has {len(entries)} item(s)." if entries else "You don't have any outfit history yet."
        return {"action": tool, "message": message, "data": {"history": entries}}

    if tool == "reminder_lookup":
        rows = db.scalars(select(AppNotification).where(AppNotification.user_id == user_id, AppNotification.status == "unread").order_by(AppNotification.scheduled_for).limit(10)).all()
        reminders = [{"title": row.title, "message": row.message, "scheduled_for": row.scheduled_for.isoformat()} for row in rows]
        message = f"You have {len(reminders)} unread in-app reminder(s)." if reminders else "You don't have any unread in-app reminders."
        return {"action": tool, "message": message, "data": {"reminders": reminders}}

    if tool == "update_preferences":
        aliases = {"favorite_colours": "favourite_colours", "favorite_colors": "favourite_colours", "preferred_colors": "favourite_colours"}
        normalized = {aliases.get(key, key): value for key, value in arguments.items()}
        allowed = {
            "preferred_styles", "favourite_colours", "disliked_colours", "preferred_formality",
            "comfort_preferences", "traditional_preferences", "preferred_sizes", "preferred_fits",
            "shopping_budget",
        }
        update = {key: value for key, value in normalized.items() if key in allowed}
        if not update:
            return {"action": "clarification", "message": "Which style preference would you like me to update?", "data": {}}
        try:
            validated = PreferenceIn(**update).model_dump(exclude_unset=True)
        except ValidationError:
            return {"action": "clarification", "message": "I couldn't apply that preference. Please specify the style or colour clearly.", "data": {}}
        preference = db.get(UserStylePreference, user_id)
        if not preference:
            raise ConversationProviderError("Your style profile is not available.")
        for key, value in validated.items():
            setattr(preference, key, value)
        db.commit()
        return {"action": tool, "message": "Updated your style preferences.", "data": validated}

    if tool == "open_scanner":
        return {"action": tool, "message": "Opening the scanner. Choose Camera or Gallery to upload a clothing photo for analysis.", "data": {"navigate_to": "/scanner"}}

    if tool == "save_outfit":
        recommendation = db.scalar(
            select(OutfitRecommendation)
            .where(OutfitRecommendation.user_id == user_id, OutfitRecommendation.is_current.is_(True))
            .order_by(OutfitRecommendation.created_at.desc())
        )
        if not recommendation:
            return {"action": "clarification", "message": "There isn't a current outfit recommendation to save yet. Ask me to suggest an outfit first.", "data": {}}
        recommendation.status = "saved"
        event = db.get(DailyPlanEvent, recommendation.event_id)
        plan = db.get(DailyPlan, event.plan_id) if event else None
        if event and plan and plan.user_id == user_id:
            db.add(OutfitHistory(user_id=user_id, event_id=event.id, recommendation_id=recommendation.id, plan_date=plan.plan_date, event_type=event.activity_type, status="saved", outfit_signature=[item.wardrobe_item_id for item in recommendation.items]))
        db.commit()
        return {"action": tool, "message": "Saved your current outfit recommendation.", "data": {"recommendation_id": recommendation.id}}

    if tool in {"accept_current_outfit", "reject_current_outfit"}:
        recommendation = db.scalar(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id, OutfitRecommendation.is_current.is_(True)).order_by(OutfitRecommendation.created_at.desc()))
        if not recommendation:
            return {"action": "clarification", "message": "There isn't a current outfit recommendation to give feedback on yet.", "data": {}}
        event = db.get(DailyPlanEvent, recommendation.event_id)
        plan = db.get(DailyPlan, event.plan_id) if event else None
        if not event or not plan or plan.user_id != user_id:
            raise ConversationProviderError("The selected outfit is no longer available.")
        status = "accepted" if tool == "accept_current_outfit" else "rejected"
        recommendation.status = status
        db.add(OutfitHistory(user_id=user_id, event_id=event.id, recommendation_id=recommendation.id, plan_date=plan.plan_date, event_type=event.activity_type, status=status, outfit_signature=[item.wardrobe_item_id for item in recommendation.items]))
        db.commit()
        response = "Noted, you like this outfit." if status == "accepted" else "Got it, I'll avoid this outfit."
        return {"action": tool, "message": response, "data": {"recommendation_id": recommendation.id, "status": status}}

    raise ConversationProviderError("The selected voice action is not available.")


def run_voice_command(db: Session, user_id: str, request_id: str, utterance: str, language: str) -> dict[str, Any]:
    previous = db.get(VoiceCommandReceipt, request_id)
    if previous:
        if previous.user_id != user_id or previous.utterance != utterance or previous.language != language:
            raise HTTPException(status_code=409, detail="This voice request ID was already used.")
        return previous.response
    result = execute_voice_tool(db, user_id, utterance)
    if language != "en" and result["action"] != "chat":
        try:
            provider = get_text_provider()
            language_name = "Telugu" if language == "te" else "natural Telugu-English code-switching"
            result["message"] = provider.reply(
                [{"role": "user", "content": utterance}],
                f"Translate this verified StyleMate result into {language_name}. Preserve all dates, numbers, names, and facts exactly. Do not add claims or actions. Output only the translation:\n{result['message']}",
            )
        except ConversationProviderError as exc:
            result["warning"] = f"Translation unavailable; the verified response is shown in English. {exc}"
    response = {"request_id": request_id, **result}
    db.add(VoiceCommandReceipt(request_id=request_id, user_id=user_id, utterance=utterance, language=language, response=response))
    db.commit()
    return response
