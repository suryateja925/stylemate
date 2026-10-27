from .base import VisionProvider, VisionProviderError
from .gemini_provider import GeminiVisionProvider
from .openai_provider import OpenAIVisionProvider
from ..core.config import settings


def get_vision_provider() -> VisionProvider:
    if settings.ai_provider == "gemini":
        if not settings.gemini_api_key or not settings.gemini_model:
            raise VisionProviderError("Gemini is selected but GEMINI_API_KEY or GEMINI_MODEL is missing.")
        return GeminiVisionProvider(settings.gemini_api_key, settings.gemini_model)
    if settings.ai_provider == "openai":
        if not settings.openai_api_key or not settings.openai_model:
            raise VisionProviderError("OpenAI is selected but OPENAI_API_KEY or OPENAI_MODEL is missing.")
        return OpenAIVisionProvider(settings.openai_api_key, settings.openai_model)
    raise VisionProviderError("No AI provider is configured. Set AI_PROVIDER and a matching key/model in .env.")
