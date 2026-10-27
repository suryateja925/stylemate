import base64
import json
from pathlib import Path

from .base import VisionAnalysis, VisionProviderError
from .prompt import DETECTION_SCHEMA_INSTRUCTIONS
from ..core.config import settings


class OpenAIVisionProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def analyze(self, image_path: str) -> VisionAnalysis:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, timeout=float(settings.ai_request_timeout_seconds), max_retries=1)
            data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            response = client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": DETECTION_SCHEMA_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this clothing bundle using visible evidence only."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                        ],
                    },
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise VisionProviderError("OpenAI returned an empty response.")
            return VisionAnalysis.model_validate(json.loads(content))
        except VisionProviderError:
            raise
        except Exception as exc:
            raise VisionProviderError(f"OpenAI analysis failed: {exc}") from exc
