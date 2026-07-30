from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from knoarbor.core.config import ModelRetryConfig
from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.chat import (
    ChatAnswerDecision,
    ChatMessageItem,
    ChatSessionRecord,
    ChatToolTraceItem,
)
from knoarbor.semantic.contracts import load_prompt
from knoarbor.semantic.llm import (
    ChatClient,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from knoarbor.services.chat_answer import (
    ChatComposerMaterial,
    answer_messages,
    messages_chars,
    parse_json_object,
    validate_composer_markdown,
)
from knoarbor.services.chat_context import (
    latest_user_text,
    session_dialogue_context,
)
from knoarbor.services.chat_evidence import (
    ChatEvidencePlanner,
    PreparedChatAnswerEvidence,
)
from knoarbor.services.chat_model_call import run_chat_model_call


ANSWER_DECISION_PROMPT = load_prompt("wiki_chat_answer_decision.md")


@dataclass(frozen=True)
class ChatAnswerDecisionResult:
    decision: ChatAnswerDecision
    materials: tuple[ChatComposerMaterial, ...]
    prepared_evidence: PreparedChatAnswerEvidence
    completion: ChatCompletionResponse
    call_record: dict[str, object]


@dataclass
class ChatAnswerDecisionService:
    """Selects one answer authority and the exact material it authorizes."""

    evidence_planner: ChatEvidencePlanner = field(default_factory=ChatEvidencePlanner)

    def decide(
        self,
        *,
        client: ChatClient,
        current_messages: list[ChatMessageItem],
        model_context_messages: list[ChatMessage],
        existing_session: ChatSessionRecord | None,
        observations: list[ChatToolTraceItem],
        evidence_ids: list[str],
        retrieval_outcome: str,
        image_generation_available: bool,
        turn: int,
        max_tokens: int | None,
        retry: ModelRetryConfig,
        raise_if_cancelled: Callable[[], None] | None = None,
        before_model_call: Callable[[int], None] | None = None,
    ) -> ChatAnswerDecisionResult:
        prepared = self.evidence_planner.prepare_answer_evidence(observations)
        messages = answer_messages(
            ANSWER_DECISION_PROMPT,
            self._decision_prompt(
                current_messages=current_messages,
                existing_session=existing_session,
                prepared=prepared,
                retrieval_outcome=retrieval_outcome,
                image_generation_available=image_generation_available,
            ),
            context_messages=model_context_messages,
        )
        validated: dict[str, object] = {}

        def validate_completion(completion: ChatCompletionResponse) -> None:
            try:
                decision = ChatAnswerDecision.model_validate(parse_json_object(completion.content))
                materials = _validate_and_project_decision(
                    decision,
                    prepared,
                    evidence_ids=evidence_ids,
                    image_generation_available=image_generation_available,
                )
            except (ValueError, ModelOutputError) as exc:
                raise ModelOutputError(f"Chat Answer Decision violated its output contract: {exc}") from exc
            validated["decision"] = decision
            validated["materials"] = materials

        call = run_chat_model_call(
            client=client,
            request=ChatCompletionRequest(
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
                structured_output=True,
            ),
            retry=retry,
            phase="answer_decision",
            turn=turn,
            prompt_chars=messages_chars(messages),
            raise_if_cancelled=raise_if_cancelled,
            before_model_call=before_model_call,
            completion_validator=validate_completion,
        )
        decision = validated["decision"]
        materials = validated["materials"]
        assert isinstance(decision, ChatAnswerDecision)
        assert isinstance(materials, tuple)
        return ChatAnswerDecisionResult(
            decision=decision,
            materials=materials,
            prepared_evidence=prepared,
            completion=call.completion,
            call_record=call.call_record,
        )

    def _decision_prompt(
        self,
        *,
        current_messages: list[ChatMessageItem],
        existing_session: ChatSessionRecord | None,
        prepared: PreparedChatAnswerEvidence,
        retrieval_outcome: str,
        image_generation_available: bool,
    ) -> str:
        return json.dumps(
            {
                "decision_state": {
                    "raw_evidence": prepared.model_observations,
                    "retrieval_outcome": retrieval_outcome,
                    "runtime_capabilities": {
                        "generate_image": image_generation_available,
                    },
                    "conversation_context": session_dialogue_context(existing_session),
                    "latest_user_message": latest_user_text(current_messages),
                },
                "selection_checklist": [
                    "Choose mode first: useful direct Raw => raw; otherwise useful stable general knowledge => general; otherwise gap. Local-source requests never fall back to general.",
                    "Select a compact, sufficient evidence set for the requested answer; add a span only when it supplies necessary support not already covered.",
                    "Each requested fact or comparison side must use direct support from the source that actually states it; the composer may synthesize relationships without changing source ownership.",
                    "Every offered source visual already has a caption or extracted content. Select visuals relevant to a selected answer part, omit only clearly unrelated visuals, and do not require a relevant visual to outperform text. A generated-image-only request keeps visuals empty.",
                    "Finalize gap after text and image decisions. It names only unavailable content and never contains the answer.",
                ],
                "output_contract": {
                    "mode": "raw|general|gap",
                    "spans": ["authorized support_span_id"],
                    "visuals": ["authorized visual_ref"],
                    "gap": "null or a concise unsupported remainder",
                    "generated_image_prompt": ("null or one useful prompt for an explicitly requested " "new image"),
                },
            },
            ensure_ascii=False,
        )


def _validate_and_project_decision(
    decision: ChatAnswerDecision,
    prepared: PreparedChatAnswerEvidence,
    *,
    evidence_ids: list[str],
    image_generation_available: bool,
) -> tuple[ChatComposerMaterial, ...]:
    if decision.generated_image_prompt is not None and not image_generation_available:
        raise ModelOutputError("Answer Decision requested unavailable image generation.")
    span_catalog = {span.support_span_id: span for span in prepared.support_spans}
    authorized_evidence_ids = set(evidence_ids)
    unknown_spans = [span_id for span_id in decision.spans if span_id not in span_catalog]
    if unknown_spans:
        raise ModelOutputError("Answer Decision selected unknown support spans: " + ", ".join(unknown_spans))
    selected_spans = tuple(span_catalog[span_id] for span_id in decision.spans)
    evidence_owners = {span.evidence_id for span in selected_spans}
    if not evidence_owners <= authorized_evidence_ids:
        raise ModelOutputError("Answer Decision selected support outside current Query evidence.")
    unknown_visuals = [visual_ref for visual_ref in decision.visuals if visual_ref not in prepared.source_visuals]
    if unknown_visuals:
        raise ModelOutputError("Answer Decision selected unknown source visuals: " + ", ".join(unknown_visuals))
    selected_visuals = tuple((visual_ref, prepared.source_visuals[visual_ref]) for visual_ref in decision.visuals)
    if decision.generated_image_prompt is not None:
        known_internal_ids = set(span_catalog) | set(prepared.source_visuals)
        known_internal_ids.update(span.evidence_id for span in prepared.support_spans)
        validate_composer_markdown(
            decision.generated_image_prompt,
            known_internal_ids=known_internal_ids,
        )
    cross_raw_visuals = [visual_ref for visual_ref, visual in selected_visuals if visual.evidence_id not in evidence_owners]
    if cross_raw_visuals:
        raise ModelOutputError(
            "Answer Decision selected source visuals without support from the " "same Raw source: " + ", ".join(cross_raw_visuals)
        )
    owner_order = list(dict.fromkeys(span.evidence_id for span in selected_spans))
    projected: list[ChatComposerMaterial] = []
    for index, owner in enumerate(owner_order, start=1):
        owner_spans = tuple(
            sorted(
                (span for span in selected_spans if span.evidence_id == owner),
                key=lambda span: (
                    span.char_start,
                    span.char_end,
                    span.support_span_id,
                ),
            )
        )
        projected.append(
            ChatComposerMaterial(
                material_id=f"material_{index}",
                source_label=_source_label(owner_spans[0]),
                support_spans=owner_spans,
                source_visuals=tuple((visual_ref, visual) for visual_ref, visual in selected_visuals if visual.evidence_id == owner),
            )
        )
    return tuple(projected)


def _source_label(span: object) -> str:
    document_title = str(getattr(span, "document_title", None) or "").strip()
    section_title = str(getattr(span, "title", None) or "").strip()
    if document_title and section_title and document_title != section_title:
        return f"{document_title} — {section_title}"
    return document_title or section_title or "Source evidence"
