from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.chat import ChatAnswerDraft, ChatCitation, ChatCitationSpan
from knoarbor.semantic.llm import ChatCompletionResponse, ChatMessage
from knoarbor.services.chat_evidence import PreparedSourceVisual
from knoarbor.services.chat_support_spans import ChatSupportSpan


_MARKDOWN_IMAGE_RE = re.compile(r"(?<!\\)!\[[^\]\n]*\]\([^\n)]*\)")
_INTERNAL_ID_RE = re.compile(
    r"(?<!\w)(?:sp_\d+_\d+|visual_\d+_\d+|material_\d+)(?!\w)",
    re.IGNORECASE,
)
_STANDALONE_CITATION_RE = re.compile(r"(?<![\w\\])[\[［]\d{1,3}[\]］](?!\w)")


@dataclass(frozen=True)
class ChatComposerMaterial:
    material_id: str
    source_label: str
    support_spans: tuple[ChatSupportSpan, ...]
    source_visuals: tuple[tuple[str, PreparedSourceVisual], ...] = ()

    def model_payload(self) -> dict[str, object]:
        return {
            "material_id": self.material_id,
            "source_label": self.source_label,
            "raw": [span.text for span in self.support_spans],
            "visuals": [visual.model_payload(visual_ref) for visual_ref, visual in self.source_visuals],
        }


@dataclass(frozen=True)
class ChatAnswerResult:
    draft: ChatAnswerDraft
    completion: ChatCompletionResponse
    call_record: dict[str, object]
    has_supported_answer: bool = False
    has_general_answer: bool = False
    has_gap: bool = False
    selected_evidence_ids: list[str] = field(default_factory=list)


def answer_messages(
    system_prompt: str,
    state_prompt: str,
    *,
    context_messages: list[ChatMessage] | None = None,
) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=system_prompt),
        *(context_messages or []),
        ChatMessage(role="user", content=state_prompt),
    ]


def validate_composer_markdown(
    markdown: str,
    *,
    known_internal_ids: Iterable[str] = (),
) -> None:
    prose = _markdown_without_code(markdown)
    if _MARKDOWN_IMAGE_RE.search(prose):
        raise ModelOutputError("Response Composer text must not contain model-authored image Markdown.")
    if _STANDALONE_CITATION_RE.search(prose):
        raise ModelOutputError("Response Composer text must not contain model-authored citation markers.")
    if _INTERNAL_ID_RE.search(prose) or any(internal_id and internal_id in prose for internal_id in known_internal_ids):
        raise ModelOutputError("Response Composer text must not expose request-local or evidence identities.")


def _markdown_without_code(markdown: str) -> str:
    """Project prose for marker checks without treating code as citations."""

    prose: list[str] = []
    fence: str | None = None
    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        prose.append(re.sub(r"`[^`\n]*`", "", line))
    return "\n".join(prose)


def collapsed_citations(
    selected_spans: list[ChatSupportSpan],
) -> tuple[list[ChatCitation], dict[str, int]]:
    """Use one public marker per Raw unit while retaining exact used ranges."""

    source_groups: dict[tuple[str, str], list[ChatSupportSpan]] = {}
    group_order: list[tuple[str, str]] = []
    for span in selected_spans:
        key = (
            span.raw_revision_id or "",
            span.source_unit_id or span.evidence_id,
        )
        if key not in source_groups:
            source_groups[key] = []
            group_order.append(key)
        source_groups[key].append(span)

    citations: list[ChatCitation] = []
    citation_index: dict[str, int] = {}
    for index, key in enumerate(group_order, start=1):
        spans = source_groups[key]
        ordered = sorted(spans, key=lambda item: (item.char_start, item.char_end))
        clusters: list[list[ChatSupportSpan]] = []
        cluster_spans: list[ChatSupportSpan] = []
        cluster_end: int | None = None
        for span in ordered:
            if cluster_end is None or span.char_start > cluster_end:
                if cluster_spans:
                    clusters.append(cluster_spans)
                cluster_spans = [span]
                cluster_end = span.char_end
                continue
            cluster_spans.append(span)
            cluster_end = max(cluster_end, span.char_end)
        if cluster_spans:
            clusters.append(cluster_spans)
        ranges = [
            ChatCitationSpan(
                char_start=min(item.char_start for item in cluster),
                char_end=max(item.char_end for item in cluster),
            )
            for cluster in clusters
        ]
        citations.append(
            spans[0]
            .citation()
            .model_copy(
                update={
                    "char_start": ranges[0].char_start,
                    "char_end": ranges[0].char_end,
                    "spans": ranges,
                }
            )
        )
        for span in spans:
            citation_index[span.support_span_id] = index
    return citations, citation_index


def with_citation_markers(answer: str, indexes: list[int]) -> str:
    text = answer.rstrip()
    markers = " ".join(f"[{index}]" for index in dict.fromkeys(indexes))
    if _ends_with_markdown_table(text) or _ends_with_fenced_code_block(text):
        return f"{text}\n\n{markers}"
    if text.endswith(("。", ".", "！", "!", "？", "?")):
        return f"{text[:-1].rstrip()} {markers}{text[-1]}"
    return f"{text} {markers}"


def _ends_with_markdown_table(markdown: str) -> bool:
    lines = [line.strip() for line in markdown.splitlines()]
    nonempty = [line for line in lines if line]
    if len(nonempty) < 2 or "|" not in nonempty[-1]:
        return False
    return any(
        re.fullmatch(
            r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?",
            line,
        )
        for line in nonempty[:-1]
    )


def _ends_with_fenced_code_block(markdown: str) -> bool:
    nonempty = [line.strip() for line in markdown.splitlines() if line.strip()]
    if not nonempty or not nonempty[-1].startswith(("```", "~~~")):
        return False
    marker = nonempty[-1][:3]
    return sum(line.startswith(marker) for line in nonempty) >= 2


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
