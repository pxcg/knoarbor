from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote

from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.core.schemas.source_record import SourceRecordAttachment
from knoarbor.core.vault_selection import resolve_vault_group
from knoarbor.pipelines.query_batch import (
    QueryBatchExpression,
    QueryBatchPipeline,
    QueryBatchRequest,
)
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.services.vault_asset_urls import vault_asset_src
from knoarbor.storage.source_revisions import read_active_processing_records
from knoarbor.storage.vault_layout import raw_derived_assets_root


_MARKDOWN_IMAGE_TARGET_RE = re.compile(
    r"!\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
_OBSIDIAN_IMAGE_TARGET_RE = re.compile(
    r"!\[\[(?P<target>[^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]"
)


class ChatKnowledgeService:
    """Adapts the Query-owned evidence bundle to Chat presentation contracts."""

    def retrieve_knowledge_batch(
        self,
        context: ChatToolContext,
        arguments: dict[str, Any],
    ) -> ChatToolTraceItem:
        return _retrieve_knowledge_batch(context, arguments)


def retrieve_knowledge_batch(
    context: ChatToolContext,
    arguments: dict[str, Any],
) -> ChatToolTraceItem:
    return context.services.chat_knowledge.retrieve_knowledge_batch(context, arguments)


def _retrieve_knowledge_batch(
    context: ChatToolContext,
    arguments: dict[str, Any],
) -> ChatToolTraceItem:
    expressions = _batch_expressions(arguments.get("query_expressions"))
    if not expressions:
        raise UserInputError("retrieve_knowledge_batch requires query_expressions")
    result = QueryBatchPipeline().run(
        QueryBatchRequest(
            vaults=tuple(_vaults(context)),
            expressions=tuple(
                QueryBatchExpression(
                    query_id=query_id,
                    query=query,
                    region_id=region_id,
                    group_id=group_id,
                )
                for query_id, query, region_id, group_id in expressions
            ),
            raise_if_cancelled=context.raise_if_cancelled,
        )
    )

    evidence_vaults = {
        str(item.vault.path): item.vault.path
        for item in result.evidence_set.items
    }
    processing_records_by_vault = {
        vault_key: {
            record.processing_record_id: record
            for record in read_active_processing_records(vault_path) or []
        }
        for vault_key, vault_path in evidence_vaults.items()
    }
    raw_evidence: list[dict[str, object]] = []
    citations: list[ChatCitation] = []
    selected_content_chars = 0
    evidence_packet_chars = 0
    emitted_attachment_ids: set[str] = set()
    for item in result.evidence_set.items:
        read = item.read
        handle = read.handle
        raw = read.raw_evidence
        evidence_segments = [
            {
                "text": segment.text,
                "char_start": segment.char_start,
                "char_end": segment.char_end,
            }
            for segment in item.segments
        ]
        excerpt, char_start, char_end = _validated_excerpt(
            raw,
            list(item.matched_spans[0]) if item.matched_spans else None,
        )
        processing_record = processing_records_by_vault[str(item.vault.path)].get(
            raw.processing_record_id
        )
        processing_metadata = (
            processing_record.metadata
            if processing_record is not None
            and isinstance(processing_record.metadata, dict)
            else {}
        )
        document_title = str(
            processing_metadata.get("source_focus") or ""
        ).strip()
        complete_content = raw.content or raw.excerpt
        content = "\n\n".join(
            str(segment["text"])
            for segment in evidence_segments
        )
        selected_content_chars += len(complete_content)
        evidence_packet_chars += sum(
            len(str(segment["text"]))
            for segment in evidence_segments
        )
        attachments = _answer_attachments(
            item.vault.path,
            processing_record.attachments
            if processing_record is not None
            else [],
            source_text=complete_content,
            excluded_ids=emitted_attachment_ids,
        )
        emitted_attachment_ids.update(
            str(attachment["attachment_id"])
            for attachment in attachments
        )
        raw_evidence.append(
            {
                "evidence_id": handle.evidence_id,
                "source_evidence_id": raw.evidence_id,
                "raw_record_id": raw.raw_record_id,
                "raw_revision_id": raw.raw_revision_id,
                "revision_id": handle.revision_id,
                "source_unit_id": raw.source_unit_id,
                "source_record_id": raw.source_record_id,
                "processing_record_id": raw.processing_record_id,
                "source_path": raw.source_path,
                "unit_index": raw.unit_index,
                "unit_type": raw.unit_type,
                "title": raw.title,
                "document_title": document_title or raw.title,
                "excerpt": excerpt,
                "content": content,
                "evidence_segments": evidence_segments,
                "excerpt_hash": raw.excerpt_hash,
                "char_start": char_start,
                "char_end": char_end,
                "source_unit_char_start": raw.char_start,
                "source_unit_char_end": raw.char_end,
                "structural_path": raw.structural_path,
                "locator_page_paths": list(raw.locator_page_paths),
                "attachments": attachments,
                "vault_id": item.vault.vault_id,
                "vault_name": item.vault.vault_name,
                "vault_path": str(item.vault.path),
                "query_ids": list(item.query_ids),
            }
        )
        citations.append(
            ChatCitation(
                kind="raw_evidence",
                role="source",
                path=str(raw.source_path or raw.source_unit_id),
                title=str(raw.title or "Source evidence"),
                vault_id=item.vault.vault_id,
                vault_name=item.vault.vault_name,
                vault_path=str(item.vault.path),
                evidence_id=handle.evidence_id,
                raw_revision_id=raw.raw_revision_id,
                source_unit_id=raw.source_unit_id,
                char_start=char_start,
                char_end=char_end,
                reason="Selected active Raw evidence unit.",
            )
        )

    return ChatToolTraceItem(
        tool="retrieve_knowledge_batch",
        arguments=arguments,
        status="ok",
        summary=f"Retrieved {len(raw_evidence)} active Raw source unit(s) for one answer.",
        citations=citations,
        result={
            "status": result.status,
            "query_expressions": [
                {"query_id": item.query_id, "query": item.query}
                | (
                    {"region_id": item.region_id}
                    if item.region_id is not None
                    else {}
                )
                | (
                    {"group_id": item.group_id}
                    if item.group_id is not None
                    else {}
                )
                for item in result.expressions
            ],
            "query_results": list(result.query_results),
            "group_results": list(result.group_results),
            "raw_evidence": raw_evidence,
            "selected_evidence_ids": list(
                result.evidence_set.selected_evidence_ids
            ),
            "evidence_query_ids": result.evidence_set.evidence_query_ids,
            "evidence_selection_reasons": {
                evidence_id: list(reasons)
                for evidence_id, reasons in (
                    result.evidence_set.selection_reasons.items()
                )
            },
            "candidate_structural_decisions": [
                {
                    "vault_id": candidate.vault.vault_id,
                    "evidence_id": candidate.handle.evidence_id,
                    "reasons": list(
                        result.candidate_set.structural_decisions.get(
                            candidate.key,
                            (),
                        )
                    ),
                }
                for candidate in result.candidate_set.items
            ],
            "candidate_count": result.candidate_set.count,
            "global_eligible_candidate_count": (
                result.global_eligible_candidate_count
            ),
            "global_result_window": result.global_result_window,
            "evidence_count": len(result.evidence_set.items),
            "selected_content_chars": selected_content_chars,
            "evidence_packet_chars": evidence_packet_chars,
            "evidence_packet_reduction_ratio": (
                round(
                    1 - (evidence_packet_chars / selected_content_chars),
                    6,
                )
                if selected_content_chars
                else 0.0
            ),
            "raw_read_rounds": result.raw_read_rounds,
            "raw_read_count": result.raw_read_count,
            "search_elapsed_ms": result.search_elapsed_ms,
            "raw_read_elapsed_ms": result.raw_read_elapsed_ms,
            "batch_elapsed_ms": result.batch_elapsed_ms,
            "warnings": list(result.warnings),
            "factual_authority": "active_raw_source_unit",
        },
    )


def _batch_expressions(
    value: object,
) -> list[tuple[str, str, str | None, str | None]]:
    if not isinstance(value, list):
        return []
    output: list[tuple[str, str, str | None, str | None]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            query = str(item.get("query") or "").strip()
            query_id = str(item.get("query_id") or f"q{index}").strip()
            region_id = str(item.get("region_id") or "").strip()
            group_id = str(item.get("group_id") or "").strip()
        else:
            query = str(item).strip()
            query_id = f"q{index}"
            region_id = ""
            group_id = ""
        normalized = " ".join(query.casefold().split())
        key = (normalized, region_id, group_id)
        if not query or key in seen:
            continue
        seen.add(key)
        output.append(
            (query_id, query, region_id or None, group_id or None)
        )
    return output


def _vaults(context: ChatToolContext):
    request = context.request
    return resolve_vault_group(
        vault_path=request.vault_path,
        vault_id=request.vault_id,
        vault_ids=request.vault_ids,
        all_vaults=request.all_vaults,
        config_path=request.config_path,
    )


def _validated_excerpt(raw, span: object) -> tuple[str, int | None, int | None]:
    if (
        not isinstance(span, list)
        or len(span) != 2
        or not all(isinstance(item, int) for item in span)
    ):
        return raw.excerpt, raw.char_start, raw.char_end
    start, end = span
    unit_start = raw.char_start or 0
    content = raw.content or raw.excerpt
    local_start = start - unit_start
    local_end = end - unit_start
    if not (0 <= local_start < local_end <= len(content)):
        return raw.excerpt, raw.char_start, raw.char_end
    return content[local_start:local_end], start, end


def _answer_attachments(
    vault_path: Path,
    attachments: list[SourceRecordAttachment],
    *,
    source_text: str,
    excluded_ids: set[str],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for attachment in attachments:
        if attachment.attachment_id in excluded_ids:
            continue
        if attachment.attachment_type != "image" and not str(
            attachment.mime_type or ""
        ).startswith("image/"):
            continue
        if not _attachment_is_referenced(attachment, source_text):
            continue
        asset_path = _attachment_asset_path(vault_path, attachment)
        if asset_path is None:
            continue
        src = vault_asset_src(asset_path, vault_path)
        alt = (
            (attachment.topic or attachment.name)
            .replace("[", "")
            .replace("]", "")
            .replace("\n", " ")
            .strip()
        )
        output.append(
            {
                "attachment_id": attachment.attachment_id,
                "attachment_type": "image",
                "name": attachment.name,
                "topic": attachment.topic,
                "description": attachment.description,
                "source_range": attachment.source_range,
                "mime_type": attachment.mime_type,
                "content_hash": attachment.content_hash,
                "source": attachment.source,
                "asset_path": asset_path,
                "src": src,
                "markdown_src": f"![{alt or 'Source image'}]({src})",
            }
        )
    return output


def _attachment_is_referenced(
    attachment: SourceRecordAttachment,
    source_text: str,
) -> bool:
    if not source_text:
        return False
    referenced_targets = {
        _normalize_attachment_target(match.group("target"))
        for pattern in (_MARKDOWN_IMAGE_TARGET_RE, _OBSIDIAN_IMAGE_TARGET_RE)
        for match in pattern.finditer(source_text)
    }
    referenced_targets.discard("")
    if not referenced_targets:
        return False

    markdown_target = _normalize_attachment_target(
        str(
            attachment.metadata.get("markdown_target")
            or attachment.metadata.get("obsidian_target")
            or ""
        )
    )
    if markdown_target:
        return markdown_target in referenced_targets

    candidates = {
        _normalize_attachment_target(attachment.relative_path or ""),
        _normalize_attachment_target(attachment.name),
    }
    candidates.discard("")
    if candidates & referenced_targets:
        return True
    referenced_names = {Path(target).name for target in referenced_targets}
    return any(Path(candidate).name in referenced_names for candidate in candidates)


def _normalize_attachment_target(value: str) -> str:
    return unquote(value).replace("\\", "/").split("#", 1)[0].split("?", 1)[0].strip()


def _attachment_asset_path(
    vault_path: Path,
    attachment: SourceRecordAttachment,
) -> str | None:
    vault = vault_path.expanduser().resolve()
    asset_root = raw_derived_assets_root(vault).resolve()
    candidates = []
    for value in (attachment.relative_path, attachment.path):
        text = str(value or "").strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if path.is_absolute():
            candidates.append(path.resolve())
            continue
        candidates.extend(((vault / path).resolve(), (asset_root / path).resolve()))
    for candidate in candidates:
        try:
            relative = candidate.relative_to(asset_root)
        except ValueError:
            continue
        if candidate.is_file():
            return f"raw/derived/assets/{relative.as_posix()}"
    return None
