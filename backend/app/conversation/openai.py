import base64
import json

from .base import ConversationProviderError
from .prompt import SYSTEM_PROMPT, VOICE_TOOL_PROMPT
from ..core.config import settings


class OpenAITextProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def reply(self, messages: list[dict[str, str]], context: str) -> str:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, timeout=float(settings.ai_request_timeout_seconds), max_retries=1)
            response = client.chat.completions.create(
                model=self.model,
                temperature=0.4,
                messages=[
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context}"},
                    *messages[-12:],
                ],
            )
            text = response.choices[0].message.content
            if not text:
                raise ConversationProviderError("OpenAI returned an empty chat response.")
            return text.strip()
        except ConversationProviderError:
            raise
        except Exception as exc:
            raise ConversationProviderError(f"OpenAI chat failed: {exc}") from exc

    def select_tool(self, utterance: str, context: str) -> dict[str, object]:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, timeout=float(settings.ai_request_timeout_seconds), max_retries=1)
            response = client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": f"{VOICE_TOOL_PROMPT}\n\n{context}"},
                    {"role": "user", "content": utterance},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise ConversationProviderError("OpenAI returned an empty tool selection.")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ConversationProviderError("OpenAI returned an invalid tool selection.")
            return result
        except ConversationProviderError:
            raise
        except Exception as exc:
            raise ConversationProviderError(f"OpenAI tool selection failed: {exc}") from exc
