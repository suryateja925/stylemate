import json
from pathlib import Path

from .base import VisionAnalysis, VisionProviderError
from .prompt import DETECTION_SCHEMA_INSTRUCTIONS
from ..core.config import settings


class GeminiVisionProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def analyze(self, image_path: str) -> VisionAnalysis:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=settings.ai_request_timeout_seconds * 1000))
            image_bytes = Path(image_path).read_bytes()
            response = client.models.generate_content(
                model=self.model,
                contents=[
                    DETECTION_SCHEMA_INSTRUCTIONS,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            content = getattr(response, "text", None)
            if not content:
                raise VisionProviderError("Gemini returned an empty response.")
            return VisionAnalysis.model_validate(json.loads(content))
        except VisionProviderError:
            raise
        except Exception as exc:
            raise VisionProviderError(f"Gemini analysis failed: {exc}") from exc
