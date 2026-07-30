from __future__ import annotations

from knoarbor.core.schemas.chat import ChatToolTraceItem


_PERSISTED_EVIDENCE_HANDLE_KEYS = {
    "evidence_id",
    "source_evidence_id",
    "raw_record_id",
    "raw_revision_id",
    "revision_id",
    "source_unit_id",
    "source_record_id",
    "processing_record_id",
    "source_path",
    "unit_index",
    "unit_type",
    "title",
    "excerpt_hash",
    "char_start",
    "char_end",
    "source_unit_char_start",
    "source_unit_char_end",
    "structural_path",
    "document_title",
    "locator_page_paths",
    "vault_id",
    "vault_name",
    "vault_path",
}


def compact_tool_trace_for_persistence(trace: list[ChatToolTraceItem]) -> list[ChatToolTraceItem]:
    """Persist evidence handles and provenance without duplicating active Raw."""

    output: list[ChatToolTraceItem] = []
    for item in trace:
        result = dict(item.result)
        raw_evidence = result.get("raw_evidence")
        if isinstance(raw_evidence, list):
            result["raw_evidence"] = [
                _persisted_evidence_handle(evidence)
                for evidence in raw_evidence
                if isinstance(evidence, dict)
            ]
        evidence_pack = result.get("evidence_pack")
        if isinstance(evidence_pack, dict) and isinstance(evidence_pack.get("raw_evidence"), list):
            compact_pack = dict(evidence_pack)
            compact_pack["raw_evidence"] = [
                _persisted_evidence_handle(evidence)
                for evidence in evidence_pack["raw_evidence"]
                if isinstance(evidence, dict)
            ]
            result["evidence_pack"] = compact_pack
        output.append(item.model_copy(update={"result": result}))
    return output


def _persisted_evidence_handle(evidence: dict[str, object]) -> dict[str, object]:
    handle = {
        key: value
        for key, value in evidence.items()
        if key in _PERSISTED_EVIDENCE_HANDLE_KEYS
    }
    # The renderer's existing evidence locator accepts an empty excerpt. Raw
    # content is resolved from the vault when the citation is opened.
    handle["excerpt"] = ""
    return handle
