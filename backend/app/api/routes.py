from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import re

import jwt
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from ..core.config import settings
from ..database import get_db
from ..image_processing.validation import ImageValidationError, materialize_image, read_valid_image, save_crop, save_normalized_image
from ..models import (
    AppNotification,
    Conversation,
    ConversationMessage,
    ApiRateLimit,
    DeletedAccount,
    DailyPlan,
    DailyPlanEvent,
    GarmentDetection,
    OutfitHistory,
    OutfitRecommendation,
    OutfitRecommendationItem,
    PreparationTask,
    ScanSession,
    ShoppingSearch,
    UserProfile,
    UserStylePreference,
    WardrobeItem,
)
from ..schemas import (
    ConfirmRequest,
    DetectionOut,
    DetectionPatch,
    EventRecommendationsOut,
    PlanCreate,
    PlanEventIn,
    PlanOut,
    PreferenceIn,
    PreferenceOut,
    ProfileOut,
    ProfilePatch,
    ProgressOut,
    RecommendationGenerateIn,
    RecommendationItemOut,
    RecommendationOut,
    ScanOut,
    WardrobeOut,
    WardrobePatch,
    ChatMessageIn,
    ChatMessageOut,
    ChatResponse,
    NotificationOut,
    PreparationTaskOut,
    ShoppingSearchIn,
    ShoppingSearchOut,
    ShoppingResult,
    TaskSnoozeIn,
    VoiceCommandIn,
    VoiceCommandOut,
)
from ..services.recommendation import generate_for_event, recommendation_with_items
from ..services.conversation import context_for_user, provider_status
from ..services.shopping import create_search
from ..vision.base import VisionProviderError
from ..vision.factory import get_vision_provider
from ..conversation.base import ConversationProviderError
from ..conversation.factory import get_text_provider
from ..services.voice_assistant import run_voice_command
from ..services.rate_limit import enforce_rate_limit
from ..storage import MediaStorageError, create_signed_url, delete_auth_user, delete_user_objects


router = APIRouter(prefix="/api")
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_jwk_set=True, lifespan=300, timeout=5)


def _authenticated_user_id(token: str) -> str:
    if not settings.supabase_url:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if not isinstance(algorithm, str):
            raise PyJWTError("Unsupported signing algorithm.")
        issuer = f"{settings.supabase_url}/auth/v1"
        if algorithm == "HS256" and settings.supabase_jwt_secret:
            signing_key = settings.supabase_jwt_secret
        elif algorithm in {"ES256", "RS256"}:
            signing_key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
        else:
            raise PyJWTError("Unsupported signing algorithm.")
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail="The access token is invalid or expired.") from exc

    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(status_code=401, detail="The access token does not identify a valid user.")
    return user_id


def _request_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    if credentials:
        return _authenticated_user_id(credentials.credentials)
    if not settings.is_production and x_user_id and USER_ID_PATTERN.fullmatch(x_user_id):
        return x_user_id
    raise HTTPException(status_code=401, detail="A valid authenticated session is required.")


def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> str:
    user_id = _request_user_id(credentials, x_user_id)
    if db.get(DeletedAccount, user_id):
        raise HTTPException(status_code=401, detail="This account is no longer active.")
    return user_id


def account_deletion_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    return _request_user_id(credentials, x_user_id)


def ensure_user(db: Session, user_id: str) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if not user:
        user = UserProfile(id=user_id)
        db.add(user)
        db.add(UserStylePreference(user_id=user_id))
        db.commit()
        db.refresh(user)
    elif not user.preference:
        db.add(UserStylePreference(user_id=user_id))
        db.commit()
        db.refresh(user)
    return user


def media_url(path: str | None) -> str | None:
    if not path:
        return None
    if settings.storage_provider == "supabase":
        return create_signed_url(path)
    return f"/media/{path}"


def detection_response(detection: GarmentDetection) -> DetectionOut:
    return DetectionOut.model_validate({
        **detection.__dict__,
        "image_url": media_url(detection.crop_path),
    })


def scan_response(scan: ScanSession) -> ScanOut:
    return ScanOut.model_validate({
        **scan.__dict__,
        "original_image_url": media_url(scan.original_image_path),
        "detections": [detection_response(detection) for detection in scan.detections],
    })


def wardrobe_response(item: WardrobeItem) -> WardrobeOut:
    return WardrobeOut.model_validate({
        **item.__dict__,
        "image_url": media_url(item.image_path),
    })


def recommendation_response(db: Session, recommendation: OutfitRecommendation, user_id: str) -> RecommendationOut:
    output_items: list[RecommendationItemOut] = []
    for item in recommendation.items:
        wardrobe_item = db.scalar(select(WardrobeItem).where(WardrobeItem.id == item.wardrobe_item_id, WardrobeItem.user_id == user_id))
        if wardrobe_item:
            output_items.append(RecommendationItemOut(
                wardrobe_item_id=item.wardrobe_item_id,
                slot=item.slot,
                wardrobe_item=wardrobe_response(wardrobe_item),
            ))
    return RecommendationOut.model_validate({
        **recommendation.__dict__,
        "items": output_items,
    })


def _persist_analysis(db: Session, scan: ScanSession, image_path: str) -> None:
    provider = get_vision_provider()
    with materialize_image(image_path) as analysis_path:
        analysis = provider.analyze(analysis_path)
    existing_items = db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == scan.user_id, WardrobeItem.confirmation_status == "confirmed")).all()
    for payload in analysis.detections:
        bbox = payload.bounding_box
        crop_path = None
        if bbox and bbox.valid():
            crop_path = save_crop(image_path, bbox.model_dump(), user_id=scan.user_id)
        possible_duplicate = any(
            existing.category.lower() == payload.category.lower()
            and existing.primary_color
            and payload.primary_color
            and existing.primary_color.lower() == payload.primary_color.lower()
            for existing in existing_items
        )
        explanation = payload.uncertainty_explanation
        if possible_duplicate:
            explanation = f"{explanation + ' ' if explanation else ''}This may duplicate a confirmed wardrobe item; review before confirming."
        db.add(GarmentDetection(
            scan_id=scan.id,
            temporary_id=payload.temporary_id,
            category=payload.category,
            subcategory=payload.subcategory,
            primary_color=payload.primary_color,
            secondary_colors=payload.secondary_colors,
            pattern=payload.pattern,
            visibility_status=payload.visibility_status,
            confidence=payload.confidence,
            bounding_box=bbox.model_dump() if bbox else None,
            uncertainty_explanation=explanation,
            requires_review=payload.requires_review or possible_duplicate or payload.visibility_status in {"partially_occluded", "heavily_occluded", "unidentifiable"},
            crop_path=crop_path,
        ))
    scan.needs_more_photos = analysis.needs_more_photos or any(
        payload.visibility_status in {"heavily_occluded", "unidentifiable"} for payload in analysis.detections
    )
    scan.status = "NEEDS_MORE_PHOTOS" if scan.needs_more_photos else "READY_TO_CONFIRM"
    scan.error_message = None


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    db.execute(text("SELECT 1"))
    provider = provider_status()
    return {"status": "ok", "app": "stylemate-ai", "database": "ok", "text_ai": provider}


@router.get("/profile", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ProfileOut:
    return ProfileOut.model_validate(ensure_user(db, user_id))


@router.patch("/profile", response_model=ProfileOut)
def patch_profile(payload: ProfilePatch, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ProfileOut:
    user = ensure_user(db, user_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return ProfileOut.model_validate(user)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(db: Session = Depends(get_db), user_id: str = Depends(account_deletion_user_id)) -> Response:
    if not settings.supabase_service_role_key or settings.storage_provider != "supabase":
        raise HTTPException(status_code=503, detail="Account deletion is not configured.")
    try:
        delete_user_objects(user_id)
        db.execute(delete(ApiRateLimit).where(ApiRateLimit.user_id == user_id))
        user = db.get(UserProfile, user_id)
        if user:
            db.delete(user)
        if not db.get(DeletedAccount, user_id):
            db.add(DeletedAccount(id=user_id))
        db.commit()
        delete_auth_user(user_id)
    except MediaStorageError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scanner/analyze", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def analyze_bundle(image: UploadFile = File(...), db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ScanOut:
    enforce_rate_limit(db, user_id, "scanner", limit=8, window_seconds=600)
    ensure_user(db, user_id)
    try:
        decoded = await read_valid_image(image)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    image_path = save_normalized_image(decoded, user_id=user_id)
    scan = ScanSession(user_id=user_id, status="ANALYZING", original_image_path=image_path)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    try:
        _persist_analysis(db, scan, image_path)
        db.commit()
        db.refresh(scan)
    except VisionProviderError as exc:
        scan.status = "FAILED"
        scan.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        scan.status = "FAILED"
        scan.error_message = "The image could not be analyzed. Try another photo."
        db.commit()
        raise HTTPException(status_code=502, detail=scan.error_message) from exc
    return scan_response(scan)


@router.post("/scanner/{scan_id}/photos", response_model=ScanOut)
async def add_scan_photo(scan_id: str, image: UploadFile = File(...), db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ScanOut:
    scan = db.scalar(select(ScanSession).options(selectinload(ScanSession.detections)).where(ScanSession.id == scan_id, ScanSession.user_id == user_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")
    enforce_rate_limit(db, user_id, "scanner", limit=8, window_seconds=600)
    try:
        decoded = await read_valid_image(image)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    image_path = save_normalized_image(decoded, user_id=user_id)
    scan.additional_image_paths = [*(scan.additional_image_paths or []), image_path]
    scan.status = "ANALYZING"
    db.commit()
    try:
        _persist_analysis(db, scan, image_path)
        db.commit()
    except VisionProviderError as exc:
        scan.status = "FAILED"
        scan.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return scan_response(scan)


@router.get("/scanner/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ScanOut:
    scan = db.scalar(select(ScanSession).options(selectinload(ScanSession.detections)).where(ScanSession.id == scan_id, ScanSession.user_id == user_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return scan_response(scan)


@router.get("/scanner/{scan_id}/detections", response_model=list[DetectionOut])
def get_detections(scan_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[DetectionOut]:
    scan = db.scalar(select(ScanSession).where(ScanSession.id == scan_id, ScanSession.user_id == user_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")
    detections = db.scalars(select(GarmentDetection).where(GarmentDetection.scan_id == scan_id)).all()
    return [detection_response(detection) for detection in detections]


@router.patch("/scanner/{scan_id}/detections/{detection_id}", response_model=DetectionOut)
def patch_detection(scan_id: str, detection_id: str, payload: DetectionPatch, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> DetectionOut:
    detection = db.scalar(
        select(GarmentDetection).join(ScanSession).where(
            GarmentDetection.id == detection_id,
            GarmentDetection.scan_id == scan_id,
            ScanSession.user_id == user_id,
        )
    )
    if not detection:
        raise HTTPException(status_code=404, detail="Detection not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(detection, key, value)
    db.commit()
    db.refresh(detection)
    return detection_response(detection)


@router.post("/scanner/{scan_id}/confirm", response_model=list[WardrobeOut])
def confirm_detections(scan_id: str, payload: ConfirmRequest, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[WardrobeOut]:
    scan = db.scalar(select(ScanSession).where(ScanSession.id == scan_id, ScanSession.user_id == user_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")
    detections = db.scalars(select(GarmentDetection).where(GarmentDetection.scan_id == scan_id, GarmentDetection.id.in_(payload.detection_ids))).all()
    if len(detections) != len(set(payload.detection_ids)):
        raise HTTPException(status_code=400, detail="Every detection must belong to this scan.")
    saved: list[WardrobeItem] = []
    for detection in detections:
        if detection.rejected:
            continue
        existing = db.scalar(select(WardrobeItem).where(WardrobeItem.user_id == user_id, WardrobeItem.detection_id == detection.id))
        if existing:
            saved.append(existing)
            continue
        item = WardrobeItem(
            user_id=user_id,
            detection_id=detection.id,
            category=detection.category,
            subcategory=detection.subcategory,
            primary_color=detection.primary_color,
            secondary_colors=detection.secondary_colors,
            pattern=detection.pattern,
            image_path=detection.crop_path or scan.original_image_path,
        )
        db.add(item)
        detection.confirmed = True
        saved.append(item)
    scan.status = "SAVED"
    db.commit()
    for item in saved:
        db.refresh(item)
    return [wardrobe_response(item) for item in saved]


@router.get("/wardrobe", response_model=list[WardrobeOut])
def list_wardrobe(category: str | None = None, colour: str | None = None, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[WardrobeOut]:
    ensure_user(db, user_id)
    query = select(WardrobeItem).where(WardrobeItem.user_id == user_id, WardrobeItem.confirmation_status == "confirmed").order_by(WardrobeItem.created_at.desc())
    if category:
        query = query.where(WardrobeItem.category == category)
    if colour:
        query = query.where(WardrobeItem.primary_color.ilike(f"%{colour}%"))
    return [wardrobe_response(item) for item in db.scalars(query).all()]


@router.get("/wardrobe/{item_id}", response_model=WardrobeOut)
def get_wardrobe_item(item_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> WardrobeOut:
    item = db.scalar(select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.user_id == user_id))
    if not item:
        raise HTTPException(status_code=404, detail="Wardrobe item not found.")
    return wardrobe_response(item)


@router.patch("/wardrobe/{item_id}", response_model=WardrobeOut)
def patch_wardrobe_item(item_id: str, payload: WardrobePatch, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> WardrobeOut:
    item = db.scalar(select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.user_id == user_id))
    if not item:
        raise HTTPException(status_code=404, detail="Wardrobe item not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return wardrobe_response(item)


@router.delete("/wardrobe/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wardrobe_item(item_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> None:
    item = db.scalar(select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.user_id == user_id))
    if not item:
        raise HTTPException(status_code=404, detail="Wardrobe item not found.")
    db.delete(item)
    db.commit()


def save_plan_payload(db: Session, user_id: str, payload: PlanCreate, plan: DailyPlan | None = None) -> DailyPlan:
    if not plan:
        plan = db.scalar(select(DailyPlan).where(DailyPlan.user_id == user_id, DailyPlan.plan_date == payload.plan_date))
    if not plan:
        plan = DailyPlan(user_id=user_id, plan_date=payload.plan_date)
        db.add(plan)
        db.flush()
    else:
        plan.plan_date = payload.plan_date
        plan.events.clear()
        db.flush()
    for index, event_payload in enumerate(payload.events):
        db.add(DailyPlanEvent(plan_id=plan.id, order_index=index, **event_payload.model_dump()))
    db.flush()
    event_rows = db.scalars(select(DailyPlanEvent).where(DailyPlanEvent.plan_id == plan.id)).all()
    for event in event_rows:
        for task in list(event.preparation_tasks):
            db.delete(task)
        hour, minute = (int(value) for value in (event.start_time or "12:00").split(":"))
        event_at = datetime.combine(plan.plan_date, time(hour=hour, minute=minute), tzinfo=timezone.utc)
        task_templates = (
            ("outfit_selection", "Choose and save an outfit", 7),
            ("missing_garments", "Check missing garments and shopping options", 3),
            ("footwear_accessories", "Check footwear and accessories", 1),
            ("fit_cleanliness", "Check fit and cleanliness", 1),
            ("packing", "Pack or prepare the outfit", 0),
        )
        now = datetime.now(timezone.utc)
        for task_type, title, days_before in task_templates:
            due_at = max(now, event_at - timedelta(days=days_before))
            db.add(PreparationTask(user_id=user_id, event_id=event.id, task_type=task_type, title=title, due_at=due_at))
    db.commit()
    plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.id == plan.id)) or plan
    return plan


def append_plan_event(db: Session, user_id: str, plan_date: date, event_payload: PlanEventIn) -> DailyPlan:
    plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.user_id == user_id, DailyPlan.plan_date == plan_date))
    if not plan:
        plan = DailyPlan(user_id=user_id, plan_date=plan_date)
        db.add(plan)
        db.flush()
    event = DailyPlanEvent(plan_id=plan.id, order_index=len(plan.events), **event_payload.model_dump())
    db.add(event)
    db.flush()
    hour, minute = (int(value) for value in (event.start_time or "12:00").split(":"))
    event_at = datetime.combine(plan_date, time(hour=hour, minute=minute), tzinfo=timezone.utc)
    task_templates = (
        ("outfit_selection", "Choose and save an outfit", 7),
        ("missing_garments", "Check missing garments and shopping options", 3),
        ("footwear_accessories", "Check footwear and accessories", 1),
        ("fit_cleanliness", "Check fit and cleanliness", 1),
        ("packing", "Pack or prepare the outfit", 0),
    )
    now = datetime.now(timezone.utc)
    for task_type, title, days_before in task_templates:
        due_at = max(now, event_at - timedelta(days=days_before))
        db.add(PreparationTask(user_id=user_id, event_id=event.id, task_type=task_type, title=title, due_at=due_at))
    db.commit()
    return db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.id == plan.id)) or plan


@router.post("/plans", response_model=PlanOut)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PlanOut:
    ensure_user(db, user_id)
    return PlanOut.model_validate(save_plan_payload(db, user_id, payload))


@router.get("/plans", response_model=list[PlanOut])
def list_plans(plan_date: date | None = Query(default=None), db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[PlanOut]:
    query = select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.user_id == user_id).order_by(DailyPlan.plan_date.desc())
    if plan_date:
        query = query.where(DailyPlan.plan_date == plan_date)
    return [PlanOut.model_validate(plan) for plan in db.scalars(query).all()]


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PlanOut:
    plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.id == plan_id, DailyPlan.user_id == user_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return PlanOut.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def patch_plan(plan_id: str, payload: PlanCreate, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PlanOut:
    plan = db.scalar(select(DailyPlan).where(DailyPlan.id == plan_id, DailyPlan.user_id == user_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return PlanOut.model_validate(save_plan_payload(db, user_id, payload, plan))


@router.post("/plans/{plan_id}/save", response_model=PlanOut)
def save_plan(plan_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PlanOut:
    plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.id == plan_id, DailyPlan.user_id == user_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    plan.status = "saved"
    from ..models import utc_now
    plan.saved_at = utc_now()
    db.commit()
    db.refresh(plan)
    return PlanOut.model_validate(plan)


@router.post("/plans/{plan_id}/events/{event_id}/cancel", response_model=PlanOut)
def cancel_plan_event(plan_id: str, event_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PlanOut:
    plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.id == plan_id, DailyPlan.user_id == user_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    event = next((item for item in plan.events if item.id == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Plan event not found.")
    event.cancelled = True
    for task in event.preparation_tasks:
        if task.status != "completed":
            task.status = "cancelled"
    db.commit()
    db.refresh(plan)
    return PlanOut.model_validate(plan)


@router.get("/preparation/tasks", response_model=list[PreparationTaskOut])
def list_preparation_tasks(
    include_completed: bool = False,
    event_id: str | None = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
) -> list[PreparationTaskOut]:
    query = select(PreparationTask).where(PreparationTask.user_id == user_id).order_by(PreparationTask.due_at)
    if not include_completed:
        query = query.where(PreparationTask.status != "completed")
    if event_id:
        query = query.where(PreparationTask.event_id == event_id)
    return [PreparationTaskOut.model_validate(task) for task in db.scalars(query).all()]


@router.post("/preparation/tasks/{task_id}/complete", response_model=PreparationTaskOut)
def complete_preparation_task(task_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PreparationTaskOut:
    task = db.scalar(select(PreparationTask).where(PreparationTask.id == task_id, PreparationTask.user_id == user_id))
    if not task:
        raise HTTPException(status_code=404, detail="Preparation task not found.")
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return PreparationTaskOut.model_validate(task)


@router.post("/preparation/tasks/{task_id}/snooze", response_model=PreparationTaskOut)
def snooze_preparation_task(task_id: str, payload: TaskSnoozeIn, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PreparationTaskOut:
    task = db.scalar(select(PreparationTask).where(PreparationTask.id == task_id, PreparationTask.user_id == user_id))
    if not task:
        raise HTTPException(status_code=404, detail="Preparation task not found.")
    if payload.until.tzinfo is None:
        payload.until = payload.until.replace(tzinfo=timezone.utc)
    task.status = "snoozed"
    task.snoozed_until = payload.until
    task.due_at = payload.until
    db.commit()
    db.refresh(task)
    return PreparationTaskOut.model_validate(task)


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[NotificationOut]:
    rows = db.scalars(select(AppNotification).where(AppNotification.user_id == user_id, AppNotification.status == "unread").order_by(AppNotification.scheduled_for.desc())).all()
    return [NotificationOut.model_validate(row) for row in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def read_notification(notification_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> NotificationOut:
    notification = db.scalar(select(AppNotification).where(AppNotification.id == notification_id, AppNotification.user_id == user_id))
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notification.status = "read"
    db.commit()
    db.refresh(notification)
    return NotificationOut.model_validate(notification)


@router.post("/chat/messages", response_model=ChatResponse)
def chat_message(payload: ChatMessageIn, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ChatResponse:
    enforce_rate_limit(db, user_id, "chat", limit=30, window_seconds=60)
    ensure_user(db, user_id)
    conversation = None
    if payload.conversation_id:
        conversation = db.scalar(select(Conversation).where(Conversation.id == payload.conversation_id, Conversation.user_id == user_id))
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    if not conversation:
        conversation = Conversation(user_id=user_id, title=payload.content[:120])
        db.add(conversation)
        db.flush()
    language = payload.language or ("te" if any("\u0c00" <= character <= "\u0c7f" for character in payload.content) else "en")
    user_message = ConversationMessage(conversation_id=conversation.id, user_id=user_id, role="user", content=payload.content, language=language)
    db.add(user_message)
    db.flush()
    prior = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id).order_by(ConversationMessage.created_at)).all()
    try:
        provider = get_text_provider()
        answer = provider.reply([{"role": row.role, "content": row.content} for row in prior], context_for_user(db, user_id))
    except ConversationProviderError as exc:
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    assistant_message = ConversationMessage(conversation_id=conversation.id, user_id=user_id, role="assistant", content=answer, language=language)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return ChatResponse(conversation_id=conversation.id, provider=provider.name, configured=True, message=ChatMessageOut.model_validate(assistant_message))


@router.get("/chat/status")
def chat_status() -> dict[str, str | bool]:
    return provider_status()


@router.post("/voice/commands", response_model=VoiceCommandOut)
def voice_command(payload: VoiceCommandIn, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> VoiceCommandOut:
    enforce_rate_limit(db, user_id, "voice", limit=20, window_seconds=60)
    ensure_user(db, user_id)
    try:
        result = run_voice_command(db, user_id, payload.request_id, payload.utterance.strip(), payload.language)
    except ConversationProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    data = dict(result.get("data", {}))
    navigate_to = data.pop("navigate_to", None)
    return VoiceCommandOut(
        request_id=result["request_id"],
        action=result["action"],
        message=result["message"],
        data=data,
        navigate_to=navigate_to,
        warning=result.get("warning"),
    )


@router.get("/chat/{conversation_id}", response_model=list[ChatMessageOut])
def get_chat(conversation_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[ChatMessageOut]:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    rows = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id, ConversationMessage.user_id == user_id).order_by(ConversationMessage.created_at)).all()
    return [ChatMessageOut.model_validate(row) for row in rows]


@router.post("/shopping/search", response_model=ShoppingSearchOut)
def shopping_search(payload: ShoppingSearchIn, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ShoppingSearchOut:
    enforce_rate_limit(db, user_id, "shopping", limit=30, window_seconds=60)
    ensure_user(db, user_id)
    search, context, links = create_search(db, user_id, payload)
    return ShoppingSearchOut(
        id=search.id,
        query=search.query,
        wardrobe_context=context,
        budget=search.budget,
        status=search.status,
        results=[ShoppingResult.model_validate(link.__dict__) for link in links],
        created_at=search.created_at,
    )


@router.get("/shopping/searches")
def shopping_searches(db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[ShoppingSearchOut]:
    rows = db.scalars(select(ShoppingSearch).where(ShoppingSearch.user_id == user_id).order_by(ShoppingSearch.created_at.desc())).all()
    return [ShoppingSearchOut(id=row.id, query=row.query, wardrobe_context=[], budget=row.budget, status=row.status, results=[ShoppingResult.model_validate(value) for value in row.results], created_at=row.created_at) for row in rows]


@router.get("/preferences", response_model=PreferenceOut)
def get_preferences(db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PreferenceOut:
    user = ensure_user(db, user_id)
    return PreferenceOut.model_validate(user.preference)


@router.patch("/preferences", response_model=PreferenceOut)
def patch_preferences(payload: PreferenceIn, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> PreferenceOut:
    user = ensure_user(db, user_id)
    preference = user.preference
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(preference, key, value)
    db.commit()
    db.refresh(preference)
    return PreferenceOut.model_validate(preference)


@router.post("/outfits/generate", response_model=list[EventRecommendationsOut])
def generate_outfits(payload: RecommendationGenerateIn, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[EventRecommendationsOut]:
    plan = db.scalar(select(DailyPlan).options(selectinload(DailyPlan.events)).where(DailyPlan.id == payload.plan_id, DailyPlan.user_id == user_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    events = [event for event in plan.events if not event.cancelled and (not payload.event_id or event.id == payload.event_id)]
    if payload.event_id and not events:
        raise HTTPException(status_code=404, detail="Plan event not found.")
    output: list[EventRecommendationsOut] = []
    for event in events:
        recommendations = generate_for_event(db, user_id, plan, event, replace=bool(payload.event_id))
        loaded = [recommendation_with_items(db, recommendation.id, user_id) for recommendation in recommendations]
        output.append(EventRecommendationsOut(event=event, recommendations=[recommendation_response(db, row, user_id) for row in loaded if row]))
    return output


@router.post("/outfits/{outfit_id}/replace", response_model=list[RecommendationOut])
def replace_outfit(outfit_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[RecommendationOut]:
    recommendation = db.scalar(select(OutfitRecommendation).where(OutfitRecommendation.id == outfit_id, OutfitRecommendation.user_id == user_id))
    if not recommendation:
        raise HTTPException(status_code=404, detail="Outfit recommendation not found.")
    event = db.get(DailyPlanEvent, recommendation.event_id)
    plan = db.get(DailyPlan, event.plan_id) if event else None
    if not event or not plan or plan.user_id != user_id:
        raise HTTPException(status_code=404, detail="Outfit event not found.")
    generated = generate_for_event(db, user_id, plan, event, replace=True)
    return [recommendation_response(db, row, user_id) for row in (recommendation_with_items(db, item.id, user_id) for item in generated) if row]


def _record_history(db: Session, user_id: str, recommendation: OutfitRecommendation, status_value: str) -> None:
    event = db.get(DailyPlanEvent, recommendation.event_id)
    plan = db.get(DailyPlan, event.plan_id) if event else None
    item_ids = [item.wardrobe_item_id for item in recommendation.items]
    if event and plan:
        db.add(OutfitHistory(
            user_id=user_id,
            event_id=event.id,
            recommendation_id=recommendation.id,
            plan_date=plan.plan_date,
            event_type=event.activity_type,
            status=status_value,
            outfit_signature=item_ids,
        ))


@router.post("/outfits/{outfit_id}/accept", response_model=RecommendationOut)
def accept_outfit(outfit_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> RecommendationOut:
    recommendation = recommendation_with_items(db, outfit_id, user_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Outfit recommendation not found.")
    recommendation.status = "accepted"
    _record_history(db, user_id, recommendation, "accepted")
    db.commit()
    return recommendation_response(db, recommendation, user_id)


@router.post("/outfits/{outfit_id}/save", response_model=RecommendationOut)
def save_outfit(outfit_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> RecommendationOut:
    recommendation = recommendation_with_items(db, outfit_id, user_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Outfit recommendation not found.")
    recommendation.status = "saved"
    _record_history(db, user_id, recommendation, "saved")
    db.commit()
    return recommendation_response(db, recommendation, user_id)


@router.post("/outfits/{outfit_id}/mark-worn", response_model=RecommendationOut)
def mark_outfit_worn(outfit_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> RecommendationOut:
    recommendation = recommendation_with_items(db, outfit_id, user_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Outfit recommendation not found.")
    recommendation.status = "worn"
    _record_history(db, user_id, recommendation, "worn")
    db.commit()
    return recommendation_response(db, recommendation, user_id)


@router.post("/outfits/{outfit_id}/reject", response_model=RecommendationOut)
def reject_outfit(outfit_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> RecommendationOut:
    recommendation = recommendation_with_items(db, outfit_id, user_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Outfit recommendation not found.")
    recommendation.status = "rejected"
    _record_history(db, user_id, recommendation, "rejected")
    db.commit()
    return recommendation_response(db, recommendation, user_id)


@router.get("/outfits/history")
def outfit_history(db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> list[dict]:
    rows = db.scalars(select(OutfitHistory).where(OutfitHistory.user_id == user_id).order_by(OutfitHistory.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "plan_date": row.plan_date,
            "event_type": row.event_type,
            "status": row.status,
            "outfit_signature": row.outfit_signature,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/progress/summary", response_model=ProgressOut)
def progress_summary(db: Session = Depends(get_db), user_id: str = Depends(current_user_id)) -> ProgressOut:
    user = ensure_user(db, user_id)
    confirmed = db.scalar(select(func.count()).select_from(WardrobeItem).where(WardrobeItem.user_id == user_id, WardrobeItem.confirmation_status == "confirmed")) or 0
    scans = db.scalar(select(func.count()).select_from(ScanSession).where(ScanSession.user_id == user_id)) or 0
    successful_scans = db.scalar(select(func.count()).select_from(ScanSession).where(ScanSession.user_id == user_id, ScanSession.status.in_(["READY_TO_CONFIRM", "NEEDS_MORE_PHOTOS", "SAVED"]))) or 0
    failed_scans = db.scalar(select(func.count()).select_from(ScanSession).where(ScanSession.user_id == user_id, ScanSession.status == "FAILED")) or 0
    awaiting = db.scalar(select(func.count()).select_from(GarmentDetection).join(ScanSession).where(ScanSession.user_id == user_id, GarmentDetection.requires_review.is_(True), GarmentDetection.confirmed.is_(False), GarmentDetection.rejected.is_(False))) or 0
    generated = db.scalar(select(func.count()).select_from(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)) or 0
    saved = db.scalar(select(func.count()).select_from(OutfitHistory).where(OutfitHistory.user_id == user_id, OutfitHistory.status == "saved")) or 0
    worn = db.scalar(select(func.count()).select_from(OutfitHistory).where(OutfitHistory.user_id == user_id, OutfitHistory.status == "worn")) or 0
    upcoming_events = db.scalar(select(func.count()).select_from(DailyPlanEvent).join(DailyPlan).where(DailyPlan.user_id == user_id, DailyPlan.plan_date >= date.today(), DailyPlanEvent.cancelled.is_(False))) or 0
    completed_tasks = db.scalar(select(func.count()).select_from(PreparationTask).where(PreparationTask.user_id == user_id, PreparationTask.status == "completed")) or 0
    pending_tasks = db.scalar(select(func.count()).select_from(PreparationTask).where(PreparationTask.user_id == user_id, PreparationTask.status != "completed")) or 0
    week_start = date.today() - timedelta(days=6)
    weekly_rows = db.execute(
        select(OutfitHistory.plan_date, func.count()).where(OutfitHistory.user_id == user_id, OutfitHistory.plan_date >= week_start).group_by(OutfitHistory.plan_date).order_by(OutfitHistory.plan_date)
    ).all()
    category_rows = db.execute(
        select(WardrobeItem.category, func.count()).where(WardrobeItem.user_id == user_id, WardrobeItem.confirmation_status == "confirmed").group_by(WardrobeItem.category).order_by(WardrobeItem.category)
    ).all()
    return ProgressOut(
        confirmed_wardrobe_items=confirmed,
        bundle_scans=scans,
        successful_scans=successful_scans,
        failed_scans=failed_scans,
        awaiting_review=awaiting,
        generated_outfits=generated,
        saved_outfits=saved,
        worn_outfits=worn,
        weekly_activity=[{"date": row[0], "count": row[1]} for row in weekly_rows],
        category_coverage=[{"category": row[0], "count": row[1]} for row in category_rows],
        wardrobe_target=user.wardrobe_target,
        completion_percentage=min(round(confirmed / user.wardrobe_target * 100, 1), 100),
        upcoming_events=upcoming_events,
        completed_preparation_tasks=completed_tasks,
        pending_preparation_tasks=pending_tasks,
    )
