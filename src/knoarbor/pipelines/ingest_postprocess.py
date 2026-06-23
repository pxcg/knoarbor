from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.errors import error_info
from knoarbor.core.redaction import redact_display_text
from knoarbor.core.schemas.ingest_pipeline import IngestSourceResult
from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.wiki_lint import LintRunRequest, LintRunResult
from knoarbor.core.schemas.wiki_write import (
    WikiDraftBatchWriteItem,
    WikiDraftBatchWriteRequest,
    WikiDraftInput,
    WikiDraftWriteResponse,
)
from knoarbor.pipelines.ingest_write_policy import IngestWritePolicy
from knoarbor.pipelines.lint import WikiLintPipeline
from knoarbor.pipelines.write import WikiWritePipeline
from knoarbor.runtime import current_run_monitor
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflowResult
from knoarbor.storage.knowledge_atom_index import KnowledgeAtomPageRef, upsert_knowledge_atom_batches
from knoarbor.storage.wiki_index import relative_wiki_path


@dataclass(frozen=True)
class IngestWriteCommit:
    generated_pages: list[str]
    write_results: list[WikiDraftWriteResponse]
    policy_changes: list[str]
    atom_index_path: str | None


class IngestPostProcessor:
    """Commits approved ingest drafts and runs source-scoped maintenance."""

    def __init__(
        self,
        *,
        write_pipeline: WikiWritePipeline,
        lint_pipeline: WikiLintPipeline,
        write_policy: IngestWritePolicy | None = None,
        clear_context_cache: Callable[[], None] | None = None,
    ) -> None:
        self.write_pipeline = write_pipeline
        self.lint_pipeline = lint_pipeline
        self.write_policy = write_policy or IngestWritePolicy()
        self.clear_context_cache = clear_context_cache or (lambda: None)

    def write_approved_items(
        self,
        *,
        vault_path: Path,
        result: IngestSourceResult,
        items: list[WikiDraftBatchWriteItem],
        semantic_results: list[IngestSemanticWorkflowResult],
        segment_records: list[dict[str, object]] | None = None,
    ) -> IngestWriteCommit | None:
        if not items:
            return None

        monitor = current_run_monitor()
        if monitor:
            monitor.event(
                "pages_write_started",
                status="writing",
                stage="writing",
                current_item=result.source_id,
                message=f"Writing {len(items)} approved draft(s).",
            )
        policy_result = self.write_policy.apply(items)
        if policy_result.changes:
            result.context["write_policy"] = {"changes": policy_result.changes}
        write_response = self.write_pipeline.run(
            WikiDraftBatchWriteRequest(
                vault_path=str(vault_path),
                auto_related_links=False,
                provenance_related_links=True,
                drafts=policy_result.items,
            )
        )
        generated_pages = [
            relative_wiki_path(vault_path, Path(item.wiki_file_path))
            for item in write_response.results
        ]
        if segment_records is not None:
            attach_written_pages_to_segment_records(segment_records, generated_pages, write_response.results)
        atom_index_path = upsert_atom_index(vault_path, semantic_results, write_response.results)
        if atom_index_path:
            result.context["knowledge_atom_index_path"] = atom_index_path

        result.generated_pages = generated_pages
        self.clear_context_cache()
        result.wrote = True
        result.status = "written"
        if monitor:
            monitor.event(
                "pages_written",
                status="running",
                stage="writing",
                current_item=result.source_id,
                message=f"Wrote {len(generated_pages)} page(s).",
                payload={"generated_pages": generated_pages},
            )
        return IngestWriteCommit(
            generated_pages=generated_pages,
            write_results=write_response.results,
            policy_changes=policy_result.changes,
            atom_index_path=atom_index_path,
        )

    def run_scoped_lint(
        self,
        *,
        result: IngestSourceResult,
        vault_path: Path,
        apply_safe_fixes: bool,
        include_related: bool,
    ) -> None:
        if not result.touched_pages:
            return
        monitor = current_run_monitor()
        try:
            if monitor:
                monitor.event(
                    "scoped_lint_started",
                    status="linting",
                    stage="scoped_lint",
                    current_item=result.source_id,
                    message="Running scoped deterministic lint.",
                )
            lint_response = self.lint_pipeline.run_maintenance(
                LintRunRequest(
                    vault_path=str(vault_path),
                    scope=maintenance_scope(result),
                    mode="deterministic",
                    apply_safe_fixes=apply_safe_fixes,
                    include_related=include_related,
                    write_report=False,
                    append_ledger=False,
                )
            )
            result.scoped_lint_result = scoped_lint_result_payload(lint_response)
            if monitor:
                monitor.event(
                    "scoped_lint_finished",
                    status="running",
                    stage="scoped_lint",
                    current_item=result.source_id,
                    message="Scoped lint finished.",
                    payload=result.scoped_lint_result,
                )
        except Exception as exc:
            lint_error = error_info(exc)
            result.scoped_lint_result = {
                "error_code": lint_error.get("code"),
                "error_category": lint_error.get("category"),
                "error_retryable": lint_error.get("retryable"),
                "error_hint": lint_error.get("hint"),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }


def approved_write_items(
    *,
    semantic_result: IngestSemanticWorkflowResult,
    approved_indexes: list[int],
    source_file: str,
    privacy_config: PrivacyConfig,
) -> list[WikiDraftBatchWriteItem]:
    approved = set(approved_indexes)
    return [
        WikiDraftBatchWriteItem(
            wiki_draft=WikiDraftInput.model_validate(draft.model_dump()),
            write_action=draft.write_action,
            target_page=draft.target_page,
            source_file=source_file,
            display_source_file=display_source_file(source_file, privacy_config),
            operation_index=draft.operation_index,
        )
        for draft in semantic_result.wiki_draft_batch.drafts
        if draft.operation_index in approved
    ]


def display_source_file(source_file: str, privacy_config: PrivacyConfig) -> str:
    if not privacy_config.redact_source_paths_in_pages:
        return source_file
    return redact_display_text(source_file, privacy_config)


def scoped_lint_payload(source_result: IngestSourceResult) -> dict[str, object]:
    return {
        "scope": "latest_ingest_source",
        "source_file": source_result.source_file,
        "pages": source_result.touched_pages,
        "include_related": True,
    }


def maintenance_scope(source_result: IngestSourceResult) -> MaintenanceScope:
    return MaintenanceScope(
        scope_id=f"latest_ingest:{source_result.source_id}",
        trigger="ingest",
        source=MaintenanceScopeSource(kind="source", source_id=source_result.source_id),
        changed_pages=source_result.touched_pages,
        recommended_lint_modes=["deterministic"],
        reason=f"Post-ingest maintenance for {source_result.source_file}.",
    )


def scoped_lint_result_payload(response: LintRunResult) -> dict[str, object]:
    return response.model_dump()


def upsert_atom_index(
    vault_path: Path,
    semantic_results: list[IngestSemanticWorkflowResult],
    write_results: list[WikiDraftWriteResponse],
) -> str | None:
    batches = [
        result.knowledge_atom_batch
        for result in semantic_results
        if result.knowledge_atom_batch.entities
        or result.knowledge_atom_batch.claims
        or result.knowledge_atom_batch.relations
        or result.knowledge_atom_batch.evidence
    ]
    if not batches:
        return None
    page_refs = [
        KnowledgeAtomPageRef(
            path=relative_wiki_path(vault_path, Path(write_result.wiki_file_path)),
            source_digest_ids=_stats_string_list(write_result.stats.get("source_digest_ids")),
            atom_ids=_stats_string_list(write_result.stats.get("atom_ids")),
        )
        for write_result in write_results
    ]
    atom_index_path = upsert_knowledge_atom_batches(vault_path, batches, page_refs)
    return atom_index_path.resolve().relative_to(vault_path.expanduser().resolve()).as_posix()


def attach_written_pages_to_segment_records(
    segment_records: list[dict[str, object]],
    generated_pages: list[str],
    write_results: list[object],
) -> None:
    pages_by_segment: dict[int, list[str]] = {}
    details_by_segment: dict[int, list[dict[str, object]]] = {}
    for page, write_result in zip(generated_pages, write_results, strict=False):
        stats = _as_dict(getattr(write_result, "stats", {}))
        operation_index = stats.get("operation_index")
        if not isinstance(operation_index, int):
            continue
        segment_index = operation_index // 1000
        pages_by_segment.setdefault(segment_index, []).append(page)
        details_by_segment.setdefault(segment_index, []).append(
            {
                "path": page,
                "created": bool(stats.get("created")),
                "write_action": stats.get("write_action"),
                "target_page": stats.get("target_page"),
                "operation_index": operation_index,
                "write_details": stats.get("write_details") if isinstance(stats.get("write_details"), dict) else {},
            }
        )
    for record in segment_records:
        index = record.get("index")
        if isinstance(index, int):
            record["generated_pages"] = pages_by_segment.get(index, [])
            record["written_page_details"] = details_by_segment.get(index, [])


def _stats_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
