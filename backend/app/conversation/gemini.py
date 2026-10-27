from pathlib import Path
import json

from .base import ConversationProviderError
from .prompt import SYSTEM_PROMPT, VOICE_TOOL_PROMPT
from ..core.config import settings


class GeminiTextProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def reply(self, messages: list[dict[str, str]], context: str) -> str:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=settings.ai_request_timeout_seconds * 1000))
            transcript = "\n".join(f"{message['role']}: {message['content']}" for message in messages[-12:])
            response = client.models.generate_content(
                model=self.model,
                contents=f"{SYSTEM_PROMPT}\n\n{context}\n\nConversation:\n{transcript}\n\nReply naturally and do not output JSON.",
            )
            text = getattr(response, "text", None)
            if not text:
                raise ConversationProviderError("Gemini returned an empty chat response.")
            return text.strip()
        except ConversationProviderError:
            raise
        except Exception as exc:
            raise ConversationProviderError(f"Gemini chat failed: {exc}") from exc

    def select_tool(self, utterance: str, context: str) -> dict[str, object]:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=settings.ai_request_timeout_seconds * 1000))
            response = client.models.generate_content(
                model=self.model,
                contents=f"{VOICE_TOOL_PROMPT}\n\n{context}\n\nUser request: {utterance}",
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            content = getattr(response, "text", None)
            if not content:
                raise ConversationProviderError("Gemini returned an empty tool selection.")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ConversationProviderError("Gemini returned an invalid tool selection.")
            return result
        except ConversationProviderError:
            raise
        except Exception as exc:
            raise ConversationProviderError(f"Gemini tool selection failed: {exc}") from exc
