from typing import Protocol


class ConversationProviderError(RuntimeError):
    pass


class TextProvider(Protocol):
    name: str

    def reply(self, messages: list[dict[str, str]], context: str) -> str:
        ...

    def select_tool(self, utterance: str, context: str) -> dict[str, object]:
        ...
