from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from knoarbor.core.errors import KnoArborError, error_info
from knoarbor.core.schemas.chat import ChatEvent, ChatRequest
from knoarbor.services.chat_dependencies import ChatExecutionDependencies
from knoarbor.runtime.local_operations import OperationCancellationToken
from knoarbor.runtime.run_monitor import RunCancelled


CHAT_STREAM_HEARTBEAT_SECONDS = 5.0


async def chat_event_stream(request: ChatRequest, services: ChatExecutionDependencies) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    cancellation = OperationCancellationToken()
    current_stage = "preparing"

    def emit(name: str, payload: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (name, payload))

    def event_callback(event: ChatEvent) -> None:
        nonlocal current_stage
        payload = chat_event_payload(event)
        current_stage = str(payload.get("stage") or current_stage)
        emit(payload["event"], payload)

    def run_chat() -> None:
        try:
            response = services.chat.chat(
                request,
                services,
                event_callback=event_callback,
                cancellation=cancellation,
            )
            emit(
                "final",
                {
                    "schema_version": "chat_stream_event.v1",
                    "event": "final",
                    "message": "Chat response completed.",
                    "response": response.model_dump(mode="json"),
                },
            )
        except RunCancelled as exc:
            emit(
                "error",
                stream_error_payload(
                    str(exc),
                    code="KA-CHAT-CANCELLED",
                    category="user_input_error",
                    retryable=False,
                    stage=current_stage,
                ),
            )
        except KnoArborError as exc:
            emit("error", stream_exception_payload(exc, stage=current_stage))
        except Exception as exc:  # noqa: BLE001 - stream errors must be serialized instead of escaping mid-response.
            emit("error", stream_exception_payload(exc, stage=current_stage))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(run_chat))
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=CHAT_STREAM_HEARTBEAT_SECONDS)
            except TimeoutError:
                # Electron proxies the local service through a custom protocol.
                # Keep the byte stream active while a provider is generating
                # without inventing a user-visible Chat event.
                yield sse_heartbeat()
                continue
            if item is None:
                break
            name, payload = item
            yield sse_event(name, payload)
    finally:
        cancellation.stop()
        await asyncio.shield(task)


def chat_event_payload(event: ChatEvent) -> dict[str, Any]:
    if event.event_type == "answer_delta":
        stream_event = "answer_delta"
    elif event.event_type == "answer_source_selected":
        stream_event = "source"
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
    if event.event_type == "answer_source_selected":
        return "generating"
    if event.event_type.startswith("tool_"):
        return "retrieving"
    if event.event_type == "model_call_started":
        phase = event.payload.get("phase")
        return "generating" if phase in {"answer", "final_answer"} else "planning"
    if event.event_type == "model_call_finished":
        phase = event.payload.get("phase")
        return "generating" if phase in {"answer", "final_answer"} else "planning"
    if event.event_type == "final_answer_ready":
        return "completed"
    if event.event_type == "answer_delta":
        return "generating"
    return "running"


def stream_exception_payload(exc: BaseException, *, stage: str) -> dict[str, Any]:
    info = error_info(exc)
    return stream_error_payload(
        str(info["message"]),
        code=info["code"],
        category=info["category"],
        retryable=info["retryable"],
        hint=info["hint"],
        stage=stage,
    )


def stream_error_payload(
    message: str,
    *,
    code: object = None,
    category: object = None,
    retryable: object = None,
    hint: object = None,
    stage: object = None,
) -> dict[str, Any]:
    return {
        "schema_version": "chat_stream_event.v1",
        "event": "error",
        "message": message,
        "error": {
            "code": str(code or "KA-CHAT-STREAM"),
            "category": str(category or "internal_error"),
            "retryable": bool(retryable) if retryable is not None else False,
            "message": message,
            "hint": str(hint or ""),
            "stage": str(stage or "running"),
        },
    }


def sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_heartbeat() -> str:
    return ": keep-alive\n\n"
