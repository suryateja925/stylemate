from datetime import date, timedelta
import io
from uuid import uuid4

from PIL import Image

from backend.app.api import routes
from backend.app.services import voice_assistant
from backend.app.vision.base import BoundingBox, DetectionPayload, VisionAnalysis


def image_file(name: str = "bundle.jpg") -> tuple[str, io.BytesIO, str]:
    image = Image.new("RGB", (240, 240), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)
    return name, buffer, "image/jpeg"


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, image_path: str) -> VisionAnalysis:
        self.calls += 1
        payloads = [
            DetectionPayload(
                temporary_id=f"top-{self.calls}", category="shirt", primary_color="navy", visibility_status="mostly_visible", confidence=0.95,
                bounding_box=BoundingBox(x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.6), requires_review=False,
            ),
            DetectionPayload(
                temporary_id=f"bottom-{self.calls}", category="jeans", primary_color="blue", visibility_status="mostly_visible", confidence=0.92,
                bounding_box=BoundingBox(x_min=0.1, y_min=0.5, x_max=0.9, y_max=0.98), requires_review=False,
            ),
            DetectionPayload(
                temporary_id=f"shoe-{self.calls}", category="footwear", primary_color="white", visibility_status="mostly_visible", confidence=0.88,
                bounding_box=BoundingBox(x_min=0.2, y_min=0.2, x_max=0.8, y_max=0.45), requires_review=False,
            ),
        ]
        return VisionAnalysis(detections=[payloads[self.calls - 1]])


class FakeVoiceProvider:
    name = "fake"

    def __init__(self, decision):
        self.decision = decision
        self.calls = 0
        self.reply_calls = 0
        self.contexts = []

    def select_tool(self, utterance, context):
        self.calls += 1
        self.contexts.append(context)
        return self.decision

    def reply(self, messages, context):
        self.reply_calls += 1
        return "Translated confirmed result"


def headers(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


def test_upload_validation_and_confirmed_wardrobe(client, monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(routes, "get_vision_provider", lambda: provider)
    response = client.post("/api/scanner/analyze", files={"image": ("bad.txt", b"not image", "text/plain")}, headers=headers("alice"))
    assert response.status_code == 400

    response = client.post("/api/scanner/analyze", files={"image": image_file()}, headers=headers("alice"))
    assert response.status_code == 201
    scan = response.json()
    assert scan["status"] == "READY_TO_CONFIRM"
    assert scan["detections"][0]["image_url"].startswith("/media/crops/")

    confirmed = client.post(f"/api/scanner/{scan['id']}/confirm", json={"detection_ids": [scan["detections"][0]["id"]]}, headers=headers("alice"))
    assert confirmed.status_code == 200
    item = confirmed.json()[0]
    assert item["confirmation_status"] == "confirmed"
    assert client.get("/api/wardrobe", headers=headers("bob")).json() == []


def test_multiple_events_filters_and_explicit_worn_status(client, monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(routes, "get_vision_provider", lambda: provider)
    item_ids: list[str] = []
    for index in range(3):
        response = client.post("/api/scanner/analyze", files={"image": image_file(f"bundle-{index}.jpg")}, headers=headers("alice"))
        assert response.status_code == 201
        scan = response.json()
        confirmed = client.post(f"/api/scanner/{scan['id']}/confirm", json={"detection_ids": [scan["detections"][0]["id"]]}, headers=headers("alice"))
        item_ids.append(confirmed.json()[0]["id"])

    plan = client.post("/api/plans", json={
        "plan_date": str(date.today()),
        "events": [
            {"activity_type": "College or university", "start_time": "09:00", "formality": "smart_casual"},
            {"activity_type": "Party or function", "start_time": "19:00", "formality": "formal"},
        ],
    }, headers=headers("alice"))
    assert plan.status_code == 200
    plan_data = plan.json()
    generated = client.post("/api/outfits/generate", json={"plan_id": plan_data["id"]}, headers=headers("alice"))
    assert generated.status_code == 200
    groups = generated.json()
    assert len(groups) == 2
    assert all(group["recommendations"] for group in groups)
    assert all(item["wardrobe_item_id"] in item_ids for group in groups for rec in group["recommendations"] for item in rec["items"])

    first_rec = groups[0]["recommendations"][0]
    assert client.get("/api/outfits/history", headers=headers("alice")).json() == []
    worn = client.post(f"/api/outfits/{first_rec['id']}/mark-worn", headers=headers("alice"))
    assert worn.status_code == 200
    history = client.get("/api/outfits/history", headers=headers("alice"))
    assert history.status_code == 200
    assert history.json()[0]["status"] == "worn"

    progress = client.get("/api/progress/summary", headers=headers("alice")).json()
    assert progress["confirmed_wardrobe_items"] == 3
    assert progress["worn_outfits"] == 1

    unavailable = client.patch(f"/api/wardrobe/{item_ids[0]}", json={"laundry_status": "in_laundry"}, headers=headers("alice"))
    assert unavailable.status_code == 200
    replacement = client.post(f"/api/outfits/{groups[1]['recommendations'][0]['id']}/replace", headers=headers("alice"))
    assert replacement.status_code == 200
    assert all(item["wardrobe_item_id"] != item_ids[0] for rec in replacement.json() for item in rec["items"])


def test_changed_plan_and_user_isolation(client):
    alice_plan = client.post("/api/plans", json={"plan_date": str(date.today() + timedelta(days=1)), "events": [{"activity_type": "Travel"}]}, headers=headers("alice"))
    bob_plan = client.post("/api/plans", json={"plan_date": str(date.today() + timedelta(days=1)), "events": [{"activity_type": "Home or relaxation"}]}, headers=headers("bob"))
    assert alice_plan.status_code == bob_plan.status_code == 200
    assert len(client.get("/api/plans", headers=headers("alice")).json()) == 1
    assert client.get("/api/plans", headers=headers("alice")).json()[0]["events"][0]["activity_type"] == "Travel"
    assert client.get("/api/plans", headers=headers("bob")).json()[0]["events"][0]["activity_type"] == "Home or relaxation"


def test_voice_command_creates_event_and_is_idempotent(client, monkeypatch):
    event_date = date.today() + timedelta(days=7)
    provider = FakeVoiceProvider({"tool": "create_event", "arguments": {"event_date": str(event_date), "activity": "Wedding"}})
    monkeypatch.setattr(voice_assistant, "get_text_provider", lambda: provider)
    existing_plan = client.post("/api/plans", json={"plan_date": str(event_date), "events": [{"activity_type": "College"}]}, headers=headers("voice-user"))
    assert existing_plan.status_code == 200
    request_id = str(uuid4())
    payload = {"request_id": request_id, "utterance": "Next week wedding undhi, event add chey", "language": "te"}

    first = client.post("/api/voice/commands", json=payload, headers=headers("voice-user"))
    second = client.post("/api/voice/commands", json=payload, headers=headers("voice-user"))

    assert first.status_code == second.status_code == 200
    assert first.json()["action"] == "create_event"
    assert first.json()["message"] == "Translated confirmed result"
    assert first.json() == second.json()
    assert provider.calls == 1
    assert provider.reply_calls == 1
    plans = client.get("/api/plans", headers=headers("voice-user")).json()
    assert len(plans) == 1
    assert len(plans[0]["events"]) == 2
    assert plans[0]["events"][1]["custom_activity"] == "Wedding"
    changed_language = client.post("/api/voice/commands", json={**payload, "language": "en"}, headers=headers("voice-user"))
    assert changed_language.status_code == 409


def test_voice_command_requires_missing_event_details_and_rejects_unregistered_tools(client, monkeypatch):
    provider = FakeVoiceProvider({"tool": "create_event", "arguments": {"activity": "Wedding"}})
    monkeypatch.setattr(voice_assistant, "get_text_provider", lambda: provider)
    response = client.post("/api/voice/commands", json={"request_id": str(uuid4()), "utterance": "Add a wedding"}, headers=headers("voice-user"))
    assert response.status_code == 200
    assert response.json()["action"] == "clarification"
    assert "date" in response.json()["message"]

    provider.decision = {"tool": "create_event", "arguments": {"event_date": str(date.today() + timedelta(days=1)), "activity": "Wedding"}}
    follow_up = client.post("/api/voice/commands", json={"request_id": str(uuid4()), "utterance": "Tomorrow"}, headers=headers("voice-user"))
    assert follow_up.status_code == 200
    assert "Recent voice conversation" in provider.contexts[-1]
    assert "What date should I add" in provider.contexts[-1]

    provider.decision = {"tool": "delete_all_data", "arguments": {}}
    rejected = client.post("/api/voice/commands", json={"request_id": str(uuid4()), "utterance": "Delete everything"}, headers=headers("voice-user"))
    assert rejected.status_code == 503


def test_voice_command_invalid_event_time_requests_clarification(client, monkeypatch):
    event_date = date.today() + timedelta(days=2)
    provider = FakeVoiceProvider({"tool": "create_event", "arguments": {"event_date": str(event_date), "activity": "Interview", "start_time": "99:99"}})
    monkeypatch.setattr(voice_assistant, "get_text_provider", lambda: provider)

    response = client.post(
        "/api/voice/commands",
        json={"request_id": str(uuid4()), "utterance": "Add interview at 99:99", "language": "en"},
        headers=headers("voice-user"),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "clarification"
    assert "valid start time" in response.json()["message"]
    assert client.get("/api/plans", headers=headers("voice-user")).json() == []


def test_voice_command_updates_explicit_user_preferences(client, monkeypatch):
    provider = FakeVoiceProvider({"tool": "update_preferences", "arguments": {"favourite_colours": ["purple"]}})
    monkeypatch.setattr(voice_assistant, "get_text_provider", lambda: provider)
    response = client.post(
        "/api/voice/commands",
        json={"request_id": str(uuid4()), "utterance": "Remember that I like purple", "language": "en"},
        headers=headers("voice-user"),
    )
    assert response.status_code == 200
    assert response.json()["action"] == "update_preferences"
    assert client.get("/api/preferences", headers=headers("voice-user")).json()["favourite_colours"] == ["purple"]


def test_voice_wardrobe_search_uses_confirmed_user_items(client, monkeypatch):
    vision = FakeProvider()
    monkeypatch.setattr(routes, "get_vision_provider", lambda: vision)
    scan = client.post("/api/scanner/analyze", files={"image": image_file()}, headers=headers("voice-user"))
    assert scan.status_code == 201
    confirmed = client.post(
        f"/api/scanner/{scan.json()['id']}/confirm",
        json={"detection_ids": [scan.json()["detections"][0]["id"]]},
        headers=headers("voice-user"),
    )
    assert confirmed.status_code == 200

    provider = FakeVoiceProvider({"tool": "wardrobe_search", "arguments": {"colour": "navy", "category": "shirt"}})
    monkeypatch.setattr(voice_assistant, "get_text_provider", lambda: provider)
    result = client.post(
        "/api/voice/commands",
        json={"request_id": str(uuid4()), "utterance": "Show my navy shirts"},
        headers=headers("voice-user"),
    )

    assert result.status_code == 200
    assert result.json()["data"]["items"][0]["colour"] == "navy"
    assert result.json()["data"]["items"][0]["category"] == "shirt"
