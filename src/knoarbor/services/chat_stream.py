from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from knoarbor.core.errors import KnoArborError
from knoarbor.core.schemas.chat import ChatEvent, ChatRequest

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


async def chat_event_stream(request: ChatRequest, services: ApplicationServices) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(name: str, payload: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (name, payload))

    def event_callback(event: ChatEvent) -> None:
        payload = chat_event_payload(event)
        emit(payload["event"], payload)

    def run_chat() -> None:
        try:
            response = services.chat.chat(request, services, event_callback=event_callback)
            emit(
                "final",
                {
                    "schema_version": "chat_stream_event.v1",
                    "event": "final",
                    "message": "Chat response completed.",
                    "response": response.model_dump(mode="json"),
                },
            )
        except KnoArborError as exc:
            emit("error", stream_error_payload(str(exc), code=getattr(exc, "code", None), retryable=getattr(exc, "retryable", None)))
        except Exception as exc:  # noqa: BLE001 - stream errors must be serialized instead of escaping mid-response.
            emit("error", stream_error_payload(str(exc)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(run_chat))
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            name, payload = item
            yield sse_event(name, payload)
    finally:
        await task


def chat_event_payload(event: ChatEvent) -> dict[str, Any]:
    if event.event_type == "answer_delta":
        stream_event = "answer_delta"
    elif event.event_type.startswith("tool_"):
        stream_event = "tool"
    elif event.event_type == "final_answer_ready":
        stream_event = "stage"
    else:
        stream_event = "stage"
    return {
        "schema_version": "chat_stream_event.v1",
        "event": stream_event,
        "message": event.message,
        "stage": chat_stage(event),
        "tool": event.tool,
        "status": event.status,
        "payload": {
            "event_type": event.event_type,
            "turn": event.turn,
            **event.payload,
        },
    }


def chat_stage(event: ChatEvent) -> str:
    if event.event_type == "chat_started":
        return "preparing"
    if event.event_type.startswith("tool_"):
        return "retrieving"
    if event.event_type == "model_call_started":
        phase = event.payload.get("phase")
        return "generating" if phase == "answer" else "planning"
    if event.event_type == "model_call_finished":
        phase = event.payload.get("phase")
        return "generating" if phase == "answer" else "planning"
    if event.event_type == "final_answer_ready":
        return "completed"
    if event.event_type == "answer_delta":
        return "generating"
    return "running"


def stream_error_payload(message: str, *, code: object = None, retryable: object = None) -> dict[str, Any]:
    return {
        "schema_version": "chat_stream_event.v1",
        "event": "error",
        "message": message,
        "error": {
            "code": str(code or "KA-CHAT-STREAM"),
            "retryable": bool(retryable) if retryable is not None else False,
            "message": message,
        },
    }


def sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
