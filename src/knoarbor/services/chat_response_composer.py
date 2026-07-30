from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Literal

from knoarbor.core.config import ModelRetryConfig
from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.chat import (
    ChatAnswerDraft,
    ChatComposerGeneratedVisualItem,
    ChatComposerSourceVisualItem,
    ChatComposerTextItem,
    ChatMessageItem,
    ChatResponseComposerDraft,
    ChatSessionRecord,
)
from knoarbor.semantic.contracts import load_prompt
from knoarbor.semantic.llm import (
    ChatClient,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from knoarbor.services.chat_answer import (
    ChatAnswerResult,
    answer_messages,
    collapsed_citations,
    messages_chars,
    parse_json_object,
    validate_composer_markdown,
    with_citation_markers,
)
from knoarbor.services.chat_answer_decision import ChatAnswerDecisionResult
from knoarbor.services.chat_context import latest_user_text, session_dialogue_context
from knoarbor.services.chat_model_call import run_chat_model_call_stream


RESPONSE_COMPOSER_PROMPT = load_prompt("wiki_chat_response_composer.md")


@dataclass(frozen=True)
class ChatGeneratedVisual:
    visual_ref: str
    description: str
    markdown: str

    def model_payload(self) -> dict[str, str]:
        return {
            "visual_ref": self.visual_ref,
            "description": self.description,
        }


@dataclass(frozen=True)
class ChatGeneratedImageState:
    status: Literal["not_requested", "failed", "available"]
    visuals: tuple[ChatGeneratedVisual, ...] = ()

    def __post_init__(self) -> None:
        if (self.status == "available") != bool(self.visuals):
            raise ValueError("available generated-image state must contain visuals, and " "other states must not")
        references = [visual.visual_ref for visual in self.visuals]
        if len(references) != len(set(references)):
            raise ValueError("generated visual references must be unique")

    def model_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "visuals": [visual.model_payload() for visual in self.visuals],
        }


@dataclass
class ChatResponseComposer:
    """Composes validated selected material without reconsidering relevance."""

    def compose(
        self,
        *,
        client: ChatClient,
        current_messages: list[ChatMessageItem],
        model_context_messages: list[ChatMessage],
        existing_session: ChatSessionRecord | None,
        decision_result: ChatAnswerDecisionResult,
        generated_image: ChatGeneratedImageState,
        turn: int,
        max_tokens: int | None,
        retry: ModelRetryConfig,
        raise_if_cancelled: Callable[[], None] | None = None,
        before_model_call: Callable[[int], None] | None = None,
    ) -> ChatAnswerResult:
        # Memory and workspace messages may inform Answer Decision, but the
        # Response Composer model receives only the validated composition state.
        del model_context_messages
        messages = answer_messages(
            RESPONSE_COMPOSER_PROMPT,
            self._composition_prompt(
                current_messages=current_messages,
                existing_session=existing_session,
                decision_result=decision_result,
                generated_image=generated_image,
            ),
        )
        validated: dict[str, object] = {}

        def validate_completion(completion: ChatCompletionResponse) -> None:
            try:
                draft = ChatResponseComposerDraft.model_validate(parse_json_object(completion.content))
                answer, citations = _validate_and_finalize_composition(
                    draft,
                    decision_result,
                    generated_image,
                )
            except (ValueError, ModelOutputError) as exc:
                raise ModelOutputError(f"Chat Response Composer violated its output contract: {exc}") from exc
            validated["draft"] = draft
            validated["answer"] = answer
            validated["citations"] = citations

        call = run_chat_model_call_stream(
            client=client,
            request=ChatCompletionRequest(
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                structured_output=True,
            ),
            retry=retry,
            phase="response_composer",
            turn=turn,
            prompt_chars=messages_chars(messages),
            raise_if_cancelled=raise_if_cancelled,
            before_model_call=before_model_call,
            completion_validator=validate_completion,
        )
        draft = validated["draft"]
        answer = validated["answer"]
        citations = validated["citations"]
        assert isinstance(draft, ChatResponseComposerDraft)
        assert isinstance(answer, str)
        assert isinstance(citations, list)
        decision = decision_result.decision
        return ChatAnswerResult(
            draft=ChatAnswerDraft(answer=answer, citations=citations),
            completion=call.completion,
            call_record=call.call_record,
            has_supported_answer=decision.mode == "raw",
            has_general_answer=decision.mode == "general",
            has_gap=decision.gap is not None,
            selected_evidence_ids=list(dict.fromkeys(citation.evidence_id for citation in citations if citation.evidence_id is not None)),
        )

    def _composition_prompt(
        self,
        *,
        current_messages: list[ChatMessageItem],
        existing_session: ChatSessionRecord | None,
        decision_result: ChatAnswerDecisionResult,
        generated_image: ChatGeneratedImageState = ChatGeneratedImageState(status="not_requested"),
    ) -> str:
        decision = decision_result.decision
        selected_visuals = [visual_ref for material in decision_result.materials for visual_ref, _ in material.source_visuals]
        first_group_end = 0
        if decision.mode == "raw":
            item_examples: list[dict[str, object]] = []
            for material in decision_result.materials:
                item_examples.append(
                    {
                        "type": "text",
                        "markdown": (
                            "natural answer Markdown explaining this material and its visuals"
                            if material.source_visuals
                            else "natural answer Markdown for this material"
                        ),
                        "materials": [material.material_id],
                    }
                )
                item_examples.extend(
                    {
                        "type": "source_visual",
                        "visual": visual_ref,
                    }
                    for visual_ref, _ in material.source_visuals
                )
                if first_group_end == 0:
                    first_group_end = len(item_examples)
        elif decision.mode == "general":
            item_examples = [
                {
                    "type": "text",
                    "markdown": "natural general-knowledge introduction",
                    "materials": [],
                }
            ]
            first_group_end = 1
            if generated_image.visuals:
                item_examples.append(
                    {
                        "type": "text",
                        "markdown": "natural continuing explanation",
                        "materials": [],
                    }
                )
        else:
            item_examples = []
        if generated_image.visuals:
            generated_examples = [
                {
                    "type": "generated_visual",
                    "visual": visual.visual_ref,
                }
                for visual in generated_image.visuals
            ]
            if first_group_end and first_group_end < len(item_examples):
                item_examples[first_group_end:first_group_end] = generated_examples
            else:
                item_examples.extend(generated_examples)
        mode_reminder = {
            "raw": (
                "Write answer text and use every listed material at least once. " "A text item's materials must support that whole item."
            ),
            "general": ("Write general-knowledge answer text with empty materials lists."),
            "gap": (
                "Return no factual text or source_visual items; place every "
                "supplied generated visual and include the required gap_markdown."
                if generated_image.visuals
                else "Return no items and only the required gap_markdown."
            ),
        }[decision.mode]
        return json.dumps(
            {
                "composition_state": {
                    "mode": decision.mode,
                    "materials": [material.model_payload() for material in decision_result.materials],
                    "gap": decision.gap,
                    "generated_image": generated_image.model_payload(),
                    "conversation_context": session_dialogue_context(existing_session),
                    "latest_user_message": latest_user_text(current_messages),
                },
                "composition_checklist": [
                    mode_reminder,
                    (
                        "Normally place every listed source visual after the first "
                        "text that specifically explains it and uses its owner "
                        "material. Use a later gallery only for a clear shared "
                        "purpose; do not move visuals to the end by default."
                        if selected_visuals
                        else "No source visual was selected; source_visual items " "are forbidden."
                    ),
                    (
                        "Place every listed generated visual exactly once "
                        "where it naturally supports the response; it is not "
                        "evidence."
                        if generated_image.visuals
                        else "Image generation failed; do not output a " "generated_visual or claim that an image was created."
                        if generated_image.status == "failed"
                        else "No generated visual was requested; generated_visual " "items are forbidden."
                    ),
                ],
                "output_contract": {
                    "items": item_examples,
                    "gap_markdown": ("required reader-facing limitation" if decision.gap is not None else None),
                },
            },
            ensure_ascii=False,
        )


def _validate_and_finalize_composition(
    draft: ChatResponseComposerDraft,
    decision_result: ChatAnswerDecisionResult,
    generated_image: ChatGeneratedImageState = ChatGeneratedImageState(status="not_requested"),
) -> tuple[str, list]:
    decision = decision_result.decision
    materials = {material.material_id: material for material in decision_result.materials}
    selected_visuals = {visual_ref for material in decision_result.materials for visual_ref, _ in material.source_visuals}
    visual_owners = {
        visual_ref: material.material_id for material in decision_result.materials for visual_ref, _ in material.source_visuals
    }
    generated_visuals = {visual.visual_ref for visual in generated_image.visuals}
    generated_visual_catalog = {visual.visual_ref: visual for visual in generated_image.visuals}
    known_internal_ids = (
        {
            value
            for material in decision_result.materials
            for span in material.support_spans
            for value in (
                material.material_id,
                span.support_span_id,
                span.evidence_id,
                span.raw_revision_id,
                span.source_unit_id,
            )
            if value
        }
        | selected_visuals
        | generated_visuals
    )
    used_materials: set[str] = set()
    placed_visuals: list[str] = []
    placed_generated_visuals: list[str] = []
    normalized_markdown: dict[int, str] = {}
    text_count = 0
    preceding_text_materials: set[str] = set()
    for item in draft.items:
        if isinstance(item, ChatComposerTextItem):
            text_count += 1
            markdown = item.markdown
            validate_composer_markdown(
                markdown,
                known_internal_ids=known_internal_ids,
            )
            normalized_markdown[id(item)] = markdown
            unknown = [material_id for material_id in item.materials if material_id not in materials]
            if unknown:
                raise ModelOutputError("Response Composer referenced unknown materials: " + ", ".join(unknown))
            used_materials.update(item.materials)
            if decision.mode == "raw" and not item.materials:
                raise ModelOutputError("Raw Response Composer text requires selected material.")
            if decision.mode != "raw" and item.materials:
                raise ModelOutputError(f"{decision.mode} Response Composer text cannot use Raw material.")
            preceding_text_materials.update(item.materials)
        elif isinstance(item, ChatComposerSourceVisualItem):
            placed_visuals.append(item.visual)
            owner = visual_owners.get(item.visual)
            if owner is None or owner not in preceding_text_materials:
                raise ModelOutputError("Response Composer source visual must follow preceding text " "using its owning material.")
        elif isinstance(item, ChatComposerGeneratedVisualItem):
            placed_generated_visuals.append(item.visual)

    if decision.mode == "raw":
        if text_count == 0:
            raise ModelOutputError("Raw Response Composer requires answer text.")
        missing_materials = set(materials) - used_materials
        if missing_materials:
            raise ModelOutputError("Response Composer omitted selected materials: " + ", ".join(sorted(missing_materials)))
    elif decision.mode == "general":
        if text_count == 0 or any(
            not isinstance(
                item,
                (ChatComposerTextItem, ChatComposerGeneratedVisualItem),
            )
            for item in draft.items
        ):
            raise ModelOutputError("General Response Composer requires text and supplied " "generated-visual items only.")
    else:
        if text_count or any(not isinstance(item, ChatComposerGeneratedVisualItem) for item in draft.items):
            raise ModelOutputError("Gap Response Composer cannot include factual answer items.")
        if draft.gap_markdown is None:
            raise ModelOutputError("Gap Response Composer requires gap_markdown.")

    if draft.gap_markdown is None and decision.gap is not None:
        raise ModelOutputError("Response Composer omitted the selected gap.")
    if draft.gap_markdown is not None and decision.gap is None:
        raise ModelOutputError("Response Composer invented an unsupported gap.")

    if set(placed_visuals) != selected_visuals or len(placed_visuals) != len(selected_visuals):
        raise ModelOutputError("Response Composer must place every selected source visual exactly once.")
    if set(placed_generated_visuals) != generated_visuals or len(placed_generated_visuals) != len(generated_visuals):
        raise ModelOutputError("Response Composer must place every generated visual exactly once.")

    selected_spans = [span for material in decision_result.materials for span in material.support_spans]
    citations, citation_index = collapsed_citations(selected_spans)
    rendered: list[str] = []
    visual_catalog = decision_result.prepared_evidence.source_visuals
    for item in draft.items:
        if isinstance(item, ChatComposerTextItem):
            indexes = [
                citation_index[span.support_span_id] for material_id in item.materials for span in materials[material_id].support_spans
            ]
            rendered.append(with_citation_markers(normalized_markdown[id(item)], indexes) if indexes else normalized_markdown[id(item)])
        elif isinstance(item, ChatComposerSourceVisualItem):
            rendered.append(visual_catalog[item.visual].markdown)
        else:
            rendered.append(generated_visual_catalog[item.visual].markdown)
    if draft.gap_markdown is not None:
        validate_composer_markdown(
            draft.gap_markdown,
            known_internal_ids=known_internal_ids,
        )
        rendered.append(draft.gap_markdown)
    answer = "\n\n".join(rendered).strip()
    if not answer:
        raise ModelOutputError("Response Composer produced an empty answer.")
    return answer, citations
