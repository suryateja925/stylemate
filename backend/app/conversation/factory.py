from .base import ConversationProviderError, TextProvider
from .gemini import GeminiTextProvider
from .openai import OpenAITextProvider
from ..core.config import settings


def get_text_provider() -> TextProvider:
    if settings.ai_provider == "gemini":
        if not settings.gemini_api_key or not settings.gemini_model:
            raise ConversationProviderError("Gemini chat is selected but GEMINI_API_KEY or GEMINI_MODEL is missing.")
        return GeminiTextProvider(settings.gemini_api_key, settings.gemini_model)
    if settings.ai_provider == "openai":
        if not settings.openai_api_key or not settings.openai_model:
            raise ConversationProviderError("OpenAI chat is selected but OPENAI_API_KEY or OPENAI_MODEL is missing.")
        return OpenAITextProvider(settings.openai_api_key, settings.openai_model)
    raise ConversationProviderError("No text AI provider is configured.")
