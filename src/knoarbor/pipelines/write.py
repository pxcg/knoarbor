from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.wiki_write import (
    VaultWriteResult,
    WikiDraft,
    WikiDraftBatchWriteRequest,
    WikiDraftBatchWriteResponse,
    WikiDraftWriteResponse,
)
from knoarbor.pipelines.draft_canonicalizer import DraftCanonicalizer
from knoarbor.runtime import runtime_logger, vault_write_lock
from knoarbor.storage import append_ingest_log, update_index
from knoarbor.storage.wiki_writer import write_draft


logger = runtime_logger(__name__)


class WikiWritePipeline:
    """Writes compiled wiki drafts and reconciles local page links."""

    def __init__(self, canonicalizer: DraftCanonicalizer | None = None) -> None:
        self.canonicalizer = canonicalizer or DraftCanonicalizer()

    def run(self, request: WikiDraftBatchWriteRequest) -> WikiDraftBatchWriteResponse:
        vault_path = Path(request.vault_path).expanduser().resolve()
        with vault_write_lock(vault_path):
            return self._run_locked(request, vault_path)

    def _run_locked(self, request: WikiDraftBatchWriteRequest, vault_path: Path) -> WikiDraftBatchWriteResponse:
        entries: list[tuple[WikiDraft, VaultWriteResult]] = []
        responses: list[WikiDraftWriteResponse] = []
        log_entries: list[tuple[WikiDraft, VaultWriteResult, str | None, str]] = []
        expected_related_by_path: dict[Path, list[str]] = {}
        logger.info("wiki_write_started drafts=%s vault=%s", len(request.drafts), vault_path)

        for item in request.drafts:
            canonicalized = self.canonicalizer.canonicalize_draft(
                item.wiki_draft,
                source_file=item.source_file,
                write_action=item.write_action,
            )
            draft = canonicalized.draft
            source_file = canonicalized.source_file
            write_result = write_draft(
                vault_path,
                draft,
                source_file,
                display_source_file=item.display_source_file,
                write_action=item.write_action,
                target_page=item.target_page,
                auto_related_links=request.auto_related_links,
            )
            entries.append((draft, write_result))
            if write_result.created or item.write_action in {"update", "merge"}:
                log_action = item.write_action if item.target_page else "create"
                log_entries.append((draft, write_result, source_file, log_action))
            expected_related_by_path[write_result.path] = [str(path).strip() for path in item.expected_related_pages if str(path).strip()]
            response = self._to_write_response(
                draft=draft,
                write_result=write_result,
                write_action=item.write_action,
                target_page=item.target_page,
            )
            response.stats["source_file"] = source_file
            response.stats["display_source_file"] = item.display_source_file or source_file
            response.stats["operation_index"] = item.operation_index
            response.stats["canonicalization_changes"] = canonicalized.changes
            responses.append(response)

        semantic_related_added_count = 0
        semantic_related_missing_count = 0
        for response in responses:
            path = Path(response.wiki_file_path)
            expected_related_pages = expected_related_by_path.get(path, [])
            if not expected_related_pages:
                continue
            response.stats["expected_related_pages"] = expected_related_pages
            response.stats["semantic_related_links"] = {"added_count": 0, "added": [], "missing": []}

        unresolved_removed_count = 0
        for response in responses:
            path = Path(response.wiki_file_path)
            content = path.read_text(encoding="utf-8")
            canonicalized_content = self.canonicalizer.canonicalize_written_content(vault_path, content)
            removed = canonicalized_content.removed_wikilinks
            if not removed:
                continue
            path.write_text(canonicalized_content.content, encoding="utf-8")
            response.wiki_md_content = canonicalized_content.content
            response.stats["unresolved_wikilinks_sanitized"] = removed
            unresolved_removed_count += len(removed)

        response = WikiDraftBatchWriteResponse(
            results=responses,
            stats={
                "written_count": len(responses),
                "batch_links_reconciled_count": 0,
                "semantic_related_links_added_count": semantic_related_added_count,
                "semantic_related_links_missing_count": semantic_related_missing_count,
                "unresolved_wikilinks_sanitized_count": unresolved_removed_count,
                "content_hashes": [result.stats.get("content_hash") for result in responses],
            },
        )
        update_index(vault_path)
        for draft, write_result, source_file, action in log_entries:
            append_ingest_log(vault_path, draft, write_result, source_file, action=action)
        logger.info("wiki_write_finished written=%s vault=%s", response.stats["written_count"], vault_path)
        return response

    def _to_write_response(
        self,
        draft: WikiDraft,
        write_result: VaultWriteResult,
        write_action: str,
        target_page: str | None,
    ) -> WikiDraftWriteResponse:
        return WikiDraftWriteResponse(
            wiki_file_path=str(write_result.path),
            wiki_md_content=write_result.content,
            stats={
                "created": write_result.created,
                "directory": draft.page_dir,
                "type": draft.page_type,
                "canonical_path": write_result.canonical_path,
                "legacy_paths": list(write_result.legacy_paths),
                "page_kind": write_result.page_kind,
                "subject_kind": write_result.subject_kind,
                "role": write_result.role,
                "facets": list(write_result.facets),
                "model_provider": draft.model_provider,
                "model_name": draft.model_name,
                "write_action": write_action,
                "target_page": target_page,
                "related_links_count": len(write_result.related_links),
                "content_hash": write_result.content_hash,
                "source_digest_ids": list(draft.source_digest_ids),
                "atom_ids": list(draft.atom_ids),
                "write_details": write_result.write_details,
            },
        )
