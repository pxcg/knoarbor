from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from knoarbor.core.schemas.chat import ChatToolTraceItem
from knoarbor.services.chat_support_spans import (
    ChatSupportSpan,
    build_support_spans,
)


CHAT_EVIDENCE_PACK_SCHEMA_VERSION = "chat_evidence_pack.v4"
CHAT_EVIDENCE_PACK_KEYS = ("kind", "raw_evidence", "citation_evidence", "fact_context_contract")


@dataclass(frozen=True)
class ChatEvidencePlanner:
    """Projects tool results into the final model's factual context."""

    def project_tool_observation(
        self,
        tool: str,
        status: str,
        summary: str,
        result: dict[str, Any],
        *,
        include_attachments: bool = True,
    ) -> dict[str, Any]:
        if tool in {"retrieve_knowledge_batch", "answer_evidence"} and isinstance(result.get("raw_evidence"), list):
            raw_evidence = [item for item in result["raw_evidence"] if isinstance(item, dict)]
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "evidence_pack": {
                    "schema_version": CHAT_EVIDENCE_PACK_SCHEMA_VERSION,
                    "kind": "query_raw_evidence",
                    "raw_evidence": [
                        _raw_evidence_payload(
                            item,
                            index=index,
                            include_attachments=include_attachments,
                        )
                        for index, item in enumerate(raw_evidence)
                    ],
                    "citation_evidence": _citation_evidence(raw_evidence),
                    "fact_context_contract": {
                        "allowed_fact_material": ["raw_evidence", "source_unit"],
                        "instruction": "Use raw_evidence as the only factual answer material.",
                    },
                },
            }
        if tool == "list_vaults":
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "default_vault_id": result.get("default_vault_id"),
                "vaults": result.get("vaults", []),
            }
        if tool == "generate_image":
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "provider": result.get("provider"),
                "model": result.get("model"),
                "prompt": result.get("prompt"),
                "images": result.get("images", []),
                "usage": result.get("usage", {}),
            }
        return {"tool": tool, "status": status, "summary": summary, "result": result}

    def project_answer_observations(
        self,
        observations: list[ChatToolTraceItem],
    ) -> list[dict[str, Any]]:
        return self.prepare_answer_evidence(observations).model_observations

    def prepare_answer_evidence(
        self,
        observations: list[ChatToolTraceItem],
    ) -> "PreparedChatAnswerEvidence":
        """Prepare the model projection and code-owned validators once."""

        raw_evidence = canonical_raw_evidence(observations)
        support_spans = tuple(
            span
            for index, item in enumerate(raw_evidence)
            for span in build_support_spans(item, evidence_index=index)
        )
        projected = [
            self.project_tool_observation(item.tool, item.status, item.summary, item.result)
            for item in observations
            if item.tool != "retrieve_knowledge_batch"
        ]
        if raw_evidence:
            projected.insert(
                0,
                {
                    "tool": "answer_evidence",
                    "status": "ok",
                    "summary": (
                        f"Forwarded {len(raw_evidence)} unique Query raw "
                        "source unit(s) to the answer."
                    ),
                    "evidence_pack": {
                        "schema_version": CHAT_EVIDENCE_PACK_SCHEMA_VERSION,
                        "kind": "query_raw_evidence",
                        "raw_evidence": [
                            _answer_model_evidence_payload(
                                item,
                                index=index,
                                support_spans=support_spans,
                            )
                            for index, item in enumerate(raw_evidence)
                        ],
                    },
                },
            )
        return PreparedChatAnswerEvidence(
            model_observations=projected,
            support_spans=support_spans,
            source_visuals=_source_visual_catalog(raw_evidence),
        )


@dataclass(frozen=True)
class PreparedSourceVisual:
    evidence_id: str
    markdown: str
    source_caption: str | None = None
    extracted_content: str | None = None

    def model_payload(self, visual_ref: str) -> dict[str, str]:
        payload = {"visual_ref": visual_ref}
        if self.source_caption:
            payload["source_caption"] = self.source_caption
        if self.extracted_content:
            payload["extracted_content"] = self.extracted_content
        return payload


@dataclass(frozen=True)
class PreparedChatAnswerEvidence:
    model_observations: list[dict[str, Any]]
    support_spans: tuple[ChatSupportSpan, ...]
    source_visuals: dict[str, PreparedSourceVisual]


def _answer_model_evidence_payload(
    item: dict[str, Any],
    *,
    index: int,
    support_spans: tuple[ChatSupportSpan, ...],
) -> dict[str, Any]:
    evidence_id = str(item.get("evidence_id") or "")
    evidence_spans = [
        span for span in support_spans if span.evidence_id == evidence_id
    ]
    excluded_image_span_ids = _source_image_markdown_span_ids(evidence_spans)
    return {
        "index": index + 1,
        "source": {
            "document_title": item.get("document_title"),
            "title": item.get("title"),
            "vault_name": item.get("vault_name"),
            "structural_path": item.get("structural_path", []),
        },
        "source_visuals": _model_attachment_payloads(
            item.get("attachments"),
            evidence_index=index,
        ),
        "support_spans": [
            {
                "support_span_id": span.support_span_id,
                "text": span.text,
            }
            for span in evidence_spans
            if span.support_span_id not in excluded_image_span_ids
        ],
    }


def _source_visual_catalog(
    raw_evidence: list[dict[str, Any]],
) -> dict[str, PreparedSourceVisual]:
    output: dict[str, PreparedSourceVisual] = {}
    for evidence_index, evidence in enumerate(raw_evidence):
        evidence_id = str(evidence.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        attachments = evidence.get("attachments", [])
        if not isinstance(attachments, list):
            continue
        for attachment_index, attachment in enumerate(attachments):
            if not isinstance(attachment, dict):
                continue
            if not _model_attachment_semantics(attachment):
                continue
            markdown = str(attachment.get("markdown_src") or "").strip()
            if not markdown:
                continue
            visual_ref = _source_visual_ref(
                evidence_index=evidence_index,
                attachment_index=attachment_index,
            )
            semantics = _model_attachment_semantics(attachment)
            output[visual_ref] = PreparedSourceVisual(
                evidence_id=evidence_id,
                markdown=markdown,
                source_caption=semantics.get("source_caption"),
                extracted_content=semantics.get("extracted_content"),
            )
    return output


def _raw_evidence_payload(
    item: dict[str, Any],
    *,
    index: int,
    include_attachments: bool,
) -> dict[str, Any]:
    support_spans = build_support_spans(item, evidence_index=index)
    return {
        "index": index + 1,
        "citation_marker": f"[{index + 1}]",
        "evidence_id": item.get("evidence_id"),
        "source_evidence_id": item.get("source_evidence_id"),
        "claim_id": item.get("claim_id"),
        "claim": item.get("claim"),
        "source_unit_id": item.get("source_unit_id"),
        "raw_record_id": item.get("raw_record_id"),
        "raw_revision_id": item.get("raw_revision_id"),
        "source_record_id": item.get("source_record_id"),
        "processing_record_id": item.get("processing_record_id"),
        "source_path": item.get("source_path"),
        "vault_id": item.get("vault_id"),
        "vault_name": item.get("vault_name"),
        "vault_path": item.get("vault_path"),
        "unit_index": item.get("unit_index"),
        "unit_type": item.get("unit_type"),
        "title": item.get("title"),
        "document_title": item.get("document_title"),
        "excerpt_hash": item.get("excerpt_hash"),
        "char_start": item.get("char_start"),
        "char_end": item.get("char_end"),
        "source_unit_char_start": item.get("source_unit_char_start"),
        "source_unit_char_end": item.get("source_unit_char_end"),
        "structural_path": item.get("structural_path", []),
        "locator_page_paths": item.get("locator_page_paths", []),
        "attachments": (
            _model_attachment_payloads(
                item.get("attachments"),
                evidence_index=index,
            )
            if include_attachments
            else []
        ),
        "support_spans": [span.model_payload() for span in support_spans],
    }


def _model_attachment_payloads(
    value: object,
    *,
    evidence_index: int,
) -> list[dict[str, str]]:
    """Expose transient visual references and useful source semantics only."""

    if not isinstance(value, list):
        return []
    payloads: list[dict[str, str]] = []
    for attachment_index, attachment in enumerate(value):
        if not isinstance(attachment, dict):
            continue
        payload = _model_attachment_semantics(attachment)
        if not payload:
            continue
        if str(attachment.get("markdown_src") or "").strip():
            payload = {
                "visual_ref": _source_visual_ref(
                    evidence_index=evidence_index,
                    attachment_index=attachment_index,
                ),
                **payload,
            }
        payloads.append(payload)
    return payloads


def _source_visual_ref(
    *,
    evidence_index: int,
    attachment_index: int,
) -> str:
    return f"visual_{evidence_index + 1}_{attachment_index + 1}"


def _source_image_markdown_span_ids(
    spans: list[ChatSupportSpan],
) -> set[str]:
    """Keep code-owned source image paths out of the answer-model projection."""

    excluded: set[str] = set()
    markdown_link = re.compile(r"\s*\[[^\]\r\n]*\]\([^\r\n]*\)\s*")
    complete_image = re.compile(r"\s*!\[[^\]\r\n]*\]\([^\r\n]*\)\s*")
    for index, span in enumerate(spans):
        if complete_image.fullmatch(span.text):
            excluded.add(span.support_span_id)
            continue
        if (
            span.text.strip() == "!"
            and index + 1 < len(spans)
            and markdown_link.fullmatch(spans[index + 1].text)
        ):
            excluded.add(span.support_span_id)
            excluded.add(spans[index + 1].support_span_id)
    return excluded


def _model_attachment_semantics(
    attachment: dict[str, Any],
) -> dict[str, str]:
    caption = str(attachment.get("topic") or "").strip()
    extracted_content = str(attachment.get("description") or "").strip()
    payload: dict[str, str] = {}
    if caption:
        payload["source_caption"] = caption
    if extracted_content and extracted_content != caption:
        payload["extracted_content"] = extracted_content
    return payload


def _citation_evidence(raw_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": index + 1,
            "citation_marker": f"[{index + 1}]",
            "kind": "source_unit",
            "evidence_id": item.get("evidence_id"),
            "source_evidence_id": item.get("source_evidence_id"),
            "claim_id": item.get("claim_id"),
            "source_unit_id": item.get("source_unit_id"),
            "source_path": item.get("source_path"),
            "title": item.get("title"),
            "excerpt_hash": item.get("excerpt_hash"),
            "vault_id": item.get("vault_id"),
            "vault_name": item.get("vault_name"),
            "vault_path": item.get("vault_path"),
        }
        for index, item in enumerate(raw_evidence)
    ]


def canonical_raw_evidence(observations: list[ChatToolTraceItem]) -> list[dict[str, Any]]:
    """Return answer-bearing claim spans once, in their first observed order."""

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for observation in observations:
        if observation.tool != "retrieve_knowledge_batch":
            continue
        result = observation.result
        citations = observation.citations
        citation_by_evidence = {
            str(citation.evidence_id): citation
            for citation in citations
            if getattr(citation, "evidence_id", None)
        }
        items = result.get("raw_evidence")
        if not isinstance(items, list):
            pack = result.get("evidence_pack")
            items = pack.get("raw_evidence") if isinstance(pack, dict) else []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            identity = str(item.get("evidence_id") or item.get("source_unit_id") or "").strip()
            if not identity or identity in seen:
                continue
            seen.add(identity)
            payload = dict(item)
            citation = citation_by_evidence.get(str(item.get("evidence_id") or ""))
            if citation is not None:
                payload.setdefault("source_path", citation.path)
                payload.setdefault("title", citation.title)
                payload.setdefault("vault_id", citation.vault_id)
                payload.setdefault("vault_name", citation.vault_name)
                payload.setdefault("vault_path", citation.vault_path)
            output.append(payload)
    return output
