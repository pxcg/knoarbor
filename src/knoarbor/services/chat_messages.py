from __future__ import annotations

from knoarbor.core.schemas.chat import ChatMessageItem


def message_key(message: ChatMessageItem) -> tuple[str, str, str | None]:
    return (message.role, message.content, message.tool_name)


def merge_messages(existing: list[ChatMessageItem], latest: list[ChatMessageItem]) -> list[ChatMessageItem]:
    """Merge a persisted conversation with a caller-provided continuation."""
    if not existing:
        return list(latest)
    if len(latest) >= len(existing) and all(
        message_key(latest[index]) == message_key(existing[index])
        for index in range(len(existing))
    ):
        return list(latest)
    merged = list(existing)
    for message in latest:
        if not merged or message_key(merged[-1]) != message_key(message):
            merged.append(message)
    return merged
