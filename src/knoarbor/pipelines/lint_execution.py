from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidate, MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.wiki_lint import WikiLintFix, WikiLintIssue
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_revisions import read_active_processing_records
from knoarbor.storage.ingest_inputs import read_input_generation
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


class LintExecutionRouter:
    """Execute approved repairs through the lifecycle that owns each artifact."""

    def __init__(
        self,
        *,
        ingest: object | None = None,
        materializer: VaultMaterializer | None = None,
        **_: object,
    ) -> None:
        self.ingest = ingest
        self.materializer = materializer or VaultMaterializer()

    def build_repair_plan(
        self,
        candidates: MaintenanceCandidates,
        review: LintMaintenanceReview,
    ) -> list[dict[str, object]]:
        queued: list[dict[str, object]] = []
        for decision in review.decisions:
            if decision.decision != "approve" or decision.operation_index >= len(candidates.candidates):
                continue
            queued.append(_governance_request(candidates.candidates[decision.operation_index], decision.model_dump()))
        return queued

    def normalize_candidates(self, candidates: MaintenanceCandidates) -> MaintenanceCandidates:
        normalized: list[MaintenanceCandidate] = []
        for candidate in candidates.candidates:
            queue_type, _owner = _request_route(candidate)
            normalized.append(
                candidate.model_copy(
                    update={
                        "executor_hint": "governance_request",
                        "recommended_action": candidate.recommended_action.model_copy(update={"action": queue_type}),
                    }
                )
            )
        return candidates.model_copy(update={"candidates": normalized})

    def collect_deterministic_actions(
        self,
        issues: list[WikiLintIssue],
        fixes: list[WikiLintFix],
    ) -> list[dict[str, object]]:
        issues_by_identity: dict[tuple[str, str], list[WikiLintIssue]] = {}
        for issue in issues:
            issues_by_identity.setdefault((issue.code, issue.path), []).append(issue)
        queued: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for fix in fixes:
            if fix.mode == "auto_applied" or not fix.action.endswith("_request") and fix.action != "report_only":
                continue
            matching_issues = issues_by_identity.get((fix.issue_code, fix.path), [])
            issue = matching_issues.pop(0) if matching_issues else None
            queue_type, owner = _deterministic_route(fix.action)
            identity = (queue_type, fix.path, fix.issue_code)
            if identity in seen:
                continue
            seen.add(identity)
            queued.append(
                {
                    "operation_index": None,
                    "queue_type": queue_type,
                    "action": queue_type,
                    "owner": owner,
                    "target": fix.path,
                    "source_record_id": None,
                    "target_page": fix.path,
                    "issue_type": fix.issue_code,
                    "source": "deterministic",
                    "risk_level": "safe" if queue_type.endswith("rebuild_request") else "low",
                    "confidence": 1.0,
                    "reason": issue.message if issue is not None else fix.description,
                    "evidence": [issue.model_dump(mode="json")] if issue is not None else [],
                    "expected_effect": fix.description,
                    "required_followups": [],
                }
            )
        return queued

    def execute(
        self,
        vault_path: str | Path,
        actions: list[dict[str, object]],
        *,
        config_path: str | None,
        vault_id: str | None,
        provider: str | None,
        max_tokens: int | None,
    ) -> list[dict[str, object]]:
        vault = Path(vault_path).expanduser().resolve()
        records = read_active_processing_records(vault) or []
        results: list[dict[str, object]] = []
        seen_sources: set[str] = set()
        rebuild_requested = False
        for action in actions:
            action_type = str(action.get("action") or "")
            if action_type in {"index_rebuild_request", "projection_rebuild_request"}:
                rebuild_requested = True
                continue
            if action_type != "reingest_request":
                results.append(_execution_result(action, status="unresolved", error="No automatic owner workflow is defined."))
                continue
            record = _resolve_source_record(records, action)
            if record is None:
                results.append(_execution_result(action, status="failed", error="The canonical source revision could not be resolved."))
                continue
            if record.raw_record_id in seen_sources:
                results.append(_execution_result(action, status="deduplicated"))
                continue
            seen_sources.add(record.raw_record_id)
            try:
                ingest = self.ingest
                if ingest is None:
                    raise RuntimeError("The lint repair router has no injected ingest owner.")
                run = ingest.start(
                    UnifiedIngestRequest(
                        kind="document",
                        execution="direct",
                        config_path=config_path,
                        source_document=_load_source_document(vault, record),
                        vault_path=str(vault),
                        vault_id=vault_id,
                        provider=provider,
                        max_tokens=max_tokens,
                        write=True,
                        write_report=True,
                        append_ledger=True,
                        force_reprocess=True,
                        auto_scoped_lint=False,
                    ),
                    foreground=True,
                )
                results.append(_execution_result(action, status="completed", run_id=run.run_id))
            except Exception as exc:
                results.append(_execution_result(action, status="failed", error=f"{type(exc).__name__}: {exc}"))
        if rebuild_requested:
            rebuild_action = next(
                action for action in actions if action.get("action") in {"index_rebuild_request", "projection_rebuild_request"}
            )
            try:
                state = self.materializer.reconcile(vault, force=True)
                status = "completed" if state.get("phase") == "clean" else "failed"
                error = None if status == "completed" else str(state.get("error") or "Materialization did not reach clean state.")
                results.append(_execution_result(rebuild_action, status=status, error=error))
            except Exception as exc:
                results.append(_execution_result(rebuild_action, status="failed", error=f"{type(exc).__name__}: {exc}"))
        return results


def _governance_request(candidate: MaintenanceCandidate, decision: dict[str, object]) -> dict[str, object]:
    queue_type, owner = _request_route(candidate)
    params = dict(candidate.recommended_action.params)
    source_record_id = _optional_text(params.get("source_record_id"))
    target = source_record_id or _optional_text(params.get("source_file")) or candidate.target_page
    return {
        "operation_index": decision.get("operation_index"),
        "queue_type": queue_type,
        "action": queue_type,
        "owner": owner,
        "target": target,
        "source_record_id": source_record_id,
        "target_page": candidate.target_page,
        "issue_type": candidate.issue_type,
        "source": candidate.source,
        "risk_level": decision.get("risk_level"),
        "confidence": min(candidate.confidence, float(decision.get("confidence") or 0.0)),
        "reason": decision.get("reason") or candidate.expected_effect,
        "evidence": [item.model_dump() for item in candidate.evidence],
        "expected_effect": candidate.expected_effect,
        "required_followups": list(decision.get("required_followups") or []),
    }


def _request_route(candidate: MaintenanceCandidate) -> tuple[str, str]:
    issue = candidate.issue_type.lower()
    action = candidate.recommended_action.action.lower()
    source = candidate.source.lower()
    if "index" in issue or "index" in action:
        return "index_rebuild_request", "index_publication"
    if source in {"provenance", "freshness"} or any(term in issue for term in ("source", "claim", "atom", "relation", "evidence", "provenance")):
        return "reingest_request", "ingest"
    if source == "quality":
        return "reingest_request", "ingest"
    return "report_only", "user"


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _deterministic_route(action: str) -> tuple[str, str]:
    if action == "reingest_request":
        return action, "ingest"
    if action == "index_rebuild_request":
        return action, "index_publication"
    if action == "projection_rebuild_request":
        return action, "projection_publication"
    return "report_only", "user"


def _resolve_source_record(records, action: dict[str, object]):
    source_record_id = _optional_text(action.get("source_record_id"))
    target_page = _optional_text(action.get("target_page"))
    target = _optional_text(action.get("target"))
    for record in records:
        if source_record_id and record.source_record_id == source_record_id:
            return record
        if target == record.raw_record_id or target == record.source.raw_path:
            return record
        if target_page and target_page in record.page_paths:
            return record
    return None


def _load_source_document(vault: Path, record) -> SourceDocument:
    if not record.revision_id:
        raise RuntimeError("The active source record has no committed revision identity.")
    store = TransactionalIngestStore(vault)
    revision = store.revision_manifest(record.revision_id)
    task_id = str(revision.get("task_id") or "")
    if not task_id:
        raise RuntimeError("The active source revision has no owning ingest task.")
    command = store.command_for_task(task_id)
    generation = read_input_generation(vault, command.generation_id)
    matches = [
        document
        for document in generation.documents
        if document.source_id == record.source.source_id
        and document.fingerprint.content_hash == record.source.content_hash
    ]
    if len(matches) != 1:
        raise RuntimeError("The immutable input generation does not contain exactly one matching source document.")
    return matches[0]


def _execution_result(
    action: dict[str, object],
    *,
    status: str,
    run_id: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "action": action.get("action"),
        "owner": action.get("owner"),
        "target": action.get("target"),
        "target_page": action.get("target_page"),
        "issue_type": action.get("issue_type"),
        "status": status,
        "run_id": run_id,
        "error": error,
    }
