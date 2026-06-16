from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.chat import ChatAnswerDraft, ChatCitation, ChatMessageItem, ChatRequest, ChatToolTraceItem
from knoarbor.services.chat_context import latest_user_text
from knoarbor.services.chat_evidence import ChatEvidencePlanner
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatCompletionResponse, ChatMessage


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
        observations: list[ChatToolTraceItem],
        turn: int,
        max_tokens: int | None,
    ) -> ChatAnswerResult:
        messages = list(initial_messages)
        messages.append(ChatMessage(role="user", content=self._evidence_prompt(current_messages, observations)))
        prompt_chars = messages_chars(messages)
        call_started = time.perf_counter()
        completion = client.complete(
            ChatCompletionRequest(
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
        )
        return ChatAnswerResult(
            draft=parse_answer_draft(completion.content),
            completion=completion,
            call_record={
                **completion.usage,
                "provider": completion.provider,
                "model": completion.model,
                "turn": turn,
                "phase": "answer",
                "prompt_chars": prompt_chars,
                "elapsed_seconds": completion.elapsed_seconds or round(time.perf_counter() - call_started, 3),
                "tokens_per_second": completion.tokens_per_second,
            },
        )

    def _evidence_prompt(self, current_messages: list[ChatMessageItem], observations: list[ChatToolTraceItem]) -> str:
        payloads = [
            self.evidence_planner.project_tool_observation(
                observation.tool,
                observation.status,
                observation.summary,
                observation.result,
            )
            for observation in observations
        ]
        return json.dumps(
            {
                "user_question": latest_user_text(current_messages),
                "tool_observations": payloads,
            },
            ensure_ascii=False,
        )


def parse_answer_draft(content: str) -> ChatAnswerDraft:
    payload = parse_json_object(content)
    payload = _normalize_answer_payload(payload)
    try:
        return ChatAnswerDraft.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise ModelOutputError(f"Chat answer model returned invalid JSON: {exc}") from exc


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


def _normalize_answer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    citations = payload.get("citations")
    if not isinstance(citations, list):
        return payload
    normalized = []
    for citation in citations:
        if not isinstance(citation, dict):
            normalized.append(citation)
            continue
        item = dict(citation)
        kind = str(item.get("kind") or "").strip().lower()
        if kind in {"concept", "entity", "comparison", "query", "workflow", "source_digest"}:
            item["kind"] = "page"
        normalized.append(item)
    return {**payload, "citations": normalized}


def final_citations(decision_citations: list[ChatCitation], trace: list[ChatToolTraceItem]) -> list[ChatCitation]:
    trace_citations = [citation for item in trace for citation in item.citations]
    if decision_citations:
        if not trace_citations:
            return _unique_citations(decision_citations)
        validated = [_enrich_citation(citation, trace_citations) for citation in decision_citations]
        validated = [citation for citation in validated if _citation_is_trace_supported(citation, trace_citations)]
        if validated:
            return _unique_citations(validated)
    return _unique_citations(trace_citations[:4])


def clean_answer_citation_paths(answer: str, citations: list[ChatCitation], *, latest_user_text: str) -> str:
    if _answer_allows_file_paths(latest_user_text):
        return answer
    cleaned = answer
    for citation in citations:
        if citation.kind != "page" or not citation.path:
            continue
        replacement = citation.title or citation.path.rsplit("/", 1)[-1].removesuffix(".md")
        path = citation.path
        cleaned = re.sub(rf"\[([^\]]+)\]\({re.escape(path)}\)", r"\1", cleaned)
        cleaned = cleaned.replace(f"`{path}`", replacement)
        cleaned = cleaned.replace(path, replacement)
    return cleaned


def _unique_citations(citations: list[ChatCitation] | Any) -> list[ChatCitation]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ChatCitation] = []
    for citation in citations:
        target = citation.path or citation.run_id or ""
        vault_identity = citation.vault_id or citation.vault_path or ""
        if not vault_identity and any(existing.kind == citation.kind and (existing.path or existing.run_id or "") == target and (existing.vault_id or existing.vault_path) for existing in unique):
            continue
        if vault_identity:
            unique = [
                existing
                for existing in unique
                if not (
                    existing.kind == citation.kind
                    and (existing.path or existing.run_id or "") == target
                    and not (existing.vault_id or existing.vault_path)
                )
            ]
            seen = {
                (existing.kind, existing.path or existing.run_id or "", existing.vault_id or existing.vault_path or "")
                for existing in unique
            }
        identity = (citation.kind, target, vault_identity)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(citation)
    return unique


def _citation_is_trace_supported(citation: ChatCitation, trace_citations: list[ChatCitation]) -> bool:
    target = citation.path or citation.run_id or ""
    return any(
        trace_citation.kind == citation.kind and (trace_citation.path or trace_citation.run_id or "") == target
        for trace_citation in trace_citations
    )


def _enrich_citation(citation: ChatCitation, trace_citations: list[ChatCitation]) -> ChatCitation:
    target = citation.path or citation.run_id or ""
    for trace_citation in trace_citations:
        if trace_citation.kind == citation.kind and (trace_citation.path or trace_citation.run_id or "") == target:
            return trace_citation.model_copy(
                update={
                    "title": citation.title or trace_citation.title,
                    "reason": citation.reason or trace_citation.reason,
                }
            )
    return citation


def _answer_allows_file_paths(latest_user_text: str) -> bool:
    path_terms = {"路径", "文件名", "文件路径", "path", "file path", "filename", "page path"}
    return any(term in latest_user_text for term in path_terms)
