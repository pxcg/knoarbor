from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from knoarbor.core.config import ModelRetryConfig
from knoarbor.core.errors import ModelOutputError
from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.chat import ChatAnswerDraft, ChatMessageItem, ChatRequest, ChatSessionRecord, ChatTopicAnchor, ChatToolTraceItem
from knoarbor.services.chat_context import latest_user_text
from knoarbor.services.chat_evidence import ChatEvidencePlanner
from knoarbor.services.chat_model_call import run_chat_model_call, run_chat_model_call_stream
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatCompletionResponse, ChatMessage


CHAT_RESPONSE_STYLES = {"concise", "balanced", "deep"}


@dataclass(frozen=True)
class ChatAnswerResult:
    draft: ChatAnswerDraft
    completion: ChatCompletionResponse
    call_record: dict[str, object]


@dataclass
class ChatAnswerSynthesizer:
    """Builds the model-facing evidence prompt and validates answer drafts."""

    evidence_planner: ChatEvidencePlanner = field(default_factory=ChatEvidencePlanner)

    def synthesize(
        self,
        *,
        client: ChatClient,
        request: ChatRequest,
        initial_messages: list[ChatMessage],
        current_messages: list[ChatMessageItem],
        existing_session: ChatSessionRecord | None,
        topic_anchor: ChatTopicAnchor | None,
        observations: list[ChatToolTraceItem],
        turn: int,
        max_tokens: int | None,
        retry: ModelRetryConfig,
        response_style: str = "balanced",
        token_callback: Callable[[str], None] | None = None,
    ) -> ChatAnswerResult:
        messages = _answer_messages(
            initial_messages,
            self._answer_prompt(current_messages, observations, existing_session, topic_anchor),
            response_style=response_style,
        )
        prompt_chars = messages_chars(messages)
        completion_request = ChatCompletionRequest(
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
            structured_output=False,
        )
        if token_callback is None:
            call = run_chat_model_call(
                client=client,
                request=completion_request,
                retry=retry,
                phase="answer",
                turn=turn,
                prompt_chars=prompt_chars,
            )
        else:
            call = run_chat_model_call_stream(
                client=client,
                request=completion_request,
                retry=retry,
                phase="answer",
                turn=turn,
                prompt_chars=prompt_chars,
                on_delta=token_callback,
            )
        return ChatAnswerResult(
            draft=ChatAnswerDraft(answer=call.completion.content.strip(), citations=[]),
            completion=call.completion,
            call_record=call.call_record,
        )

    def _answer_prompt(
        self,
        current_messages: list[ChatMessageItem],
        observations: list[ChatToolTraceItem],
        existing_session: ChatSessionRecord | None,
        topic_anchor: ChatTopicAnchor | None,
    ) -> str:
        payloads = [
            self.evidence_planner.project_tool_observation(
                observation.tool,
                observation.status,
                observation.summary,
                observation.result,
            )
            for observation in observations
        ]
        latest_user = latest_user_text(current_messages)
        return json.dumps(
            {
                "answer_state": {
                    "latest_user_message": latest_user,
                    "topic_anchor": topic_anchor.model_dump(mode="json") if topic_anchor is not None else {},
                    "recent_user_messages": _recent_user_messages(current_messages, latest_user),
                    "conversation_context": _conversation_context(existing_session),
                    "tool_observations": payloads,
                }
            },
            ensure_ascii=False,
        )


def _answer_messages(initial_messages: list[ChatMessage], answer_prompt: str, *, response_style: str = "balanced") -> list[ChatMessage]:
    """Build the answer call with stable instructions and structured state.

    Previous dialogue is passed inside the answer_state as bounded conversation
    context. It helps resolve follow-ups, while wiki tool observations remain
    the only grounding source for factual claims.
    """

    system_messages = [message for message in initial_messages if message.role == "system"]
    if not system_messages:
        raise ModelOutputError("Chat answer synthesis requires a system prompt.")
    return [*system_messages, ChatMessage(role="system", content=response_style_prompt(response_style)), ChatMessage(role="user", content=answer_prompt)]


def response_style_prompt(response_style: str) -> str:
    style = response_style if response_style in CHAT_RESPONSE_STYLES else "balanced"
    base = [
        "Response style profile:",
        f"- Default answer depth: {style}.",
        "- This is a default preference. If the latest user message explicitly asks for a shorter, longer, more detailed, or differently formatted answer, follow the latest user request for this turn.",
        "- Preserve all evidence, citation, tool, attachment, and data-handling rules from the main system prompt.",
    ]
    additions = {
        "concise": [
            "- Keep answers short unless the user explicitly asks for detail.",
            "- Include only the most important supporting evidence or citation.",
            "- Avoid long follow-up suggestions.",
        ],
        "balanced": [
            "- Give the direct answer, then the necessary explanation.",
            "- Use light structure when it helps the user scan.",
            "- Include caveats and next steps only when they materially help.",
        ],
        "deep": [
            "- Expand mechanisms, boundaries, tradeoffs, examples, and implications when evidence supports them.",
            "- Use structured sections for architecture, comparison, design, or review questions.",
            "- Distinguish confirmed evidence, reasonable synthesis, and missing context.",
        ],
    }
    return "\n".join([*base, *additions[style]])


def _conversation_context(existing_session: ChatSessionRecord | None) -> list[dict[str, object]]:
    if existing_session is None:
        return []
    context: list[dict[str, object]] = []
    for turn in existing_session.turns[-4:]:
        context.append(
            {
                "index": turn.index,
                "user_message": compact_inline_text(turn.user_message.content, 900),
                "assistant_answer": compact_inline_text(turn.assistant_message.content, 1800),
                "citation_paths": [citation.path for citation in turn.citations if citation.path],
            }
        )
    return context


def _recent_user_messages(current_messages: list[ChatMessageItem], latest_user: str) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for message in current_messages:
        if message.role != "user":
            continue
        content = message.content.strip()
        if not content or content in seen:
            continue
        seen.add(content)
        items.append(content)
    if latest_user and latest_user not in seen:
        items.append(latest_user)
    return items[-6:]


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelOutputError(f"Chat model returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ModelOutputError("Chat model returned JSON that is not an object.")
    return payload


def messages_chars(messages: list[ChatMessage]) -> int:
    return sum(len(message.content) for message in messages)
