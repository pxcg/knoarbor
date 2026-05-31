from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.lint_candidates import MaintenanceCandidate, MaintenanceEvidence, MaintenanceRecommendedAction


def source_lifecycle_candidates(
    vault_path: Path,
    state: dict[str, object],
    discovered_source_files: set[str],
) -> list[MaintenanceCandidate]:
    candidates: list[MaintenanceCandidate] = []
    for source_id, checkpoint in checkpoint_items(state.get("sources")):
        source_file = checkpoint_source_file(checkpoint)
        if not source_file or source_file_exists(vault_path, source_file):
            continue
        generated_pages = checkpoint_pages(checkpoint)
        issue_type = "source_moved_candidate" if has_same_basename(source_file, discovered_source_files) else "source_missing"
        for page in generated_pages:
            candidates.append(source_lifecycle_candidate(source_id, source_file, page, issue_type))
    for session_id, checkpoint in checkpoint_items(state.get("sessions")):
        source_file = checkpoint_source_file(checkpoint)
        if not source_file or source_file_exists(vault_path, source_file):
            continue
        for page in checkpoint_pages(checkpoint):
            candidates.append(source_lifecycle_candidate(f"hermes:{session_id}", source_file, page, "source_missing"))
    return candidates


def source_lifecycle_candidate(source_id: str, source_file: str, page: str, issue_type: str) -> MaintenanceCandidate:
    return MaintenanceCandidate(
        candidate_id=f"ingest:{issue_type}:{source_id}:{page}",
        source="provenance",
        target_page=page,
        issue_type=issue_type,
        severity="medium",
        confidence=0.85,
        risk_hint="medium",
        executor_hint="report_only",
        evidence=[
            MaintenanceEvidence(
                kind="checkpoint",
                ref=source_file,
                quote=f"Checkpoint source is no longer present: {source_file}",
            )
        ],
        recommended_action=MaintenanceRecommendedAction(
            action="review_source_lifecycle",
            params={"source_id": source_id, "source_file": source_file, "target_page": page},
        ),
        related_pages=[page],
        expected_effect="Keeps generated knowledge pages stable while routing missing or moved source provenance to lint/maintenance.",
        review_notes="Ingest reports the lifecycle event only; deletion, archive, relink, or refresh decisions belong to lint/maintenance.",
    )


def checkpoint_items(value: object) -> list[tuple[str, dict[str, object]]]:
    if not isinstance(value, dict):
        return []
    return [(str(key), item) for key, item in value.items() if isinstance(item, dict)]


def checkpoint_source_file(checkpoint: dict[str, object]) -> str | None:
    source_file = checkpoint.get("source_file")
    return source_file if isinstance(source_file, str) and source_file.strip() else None


def checkpoint_pages(checkpoint: dict[str, object]) -> list[str]:
    pages = checkpoint.get("generated_pages")
    return [str(page) for page in pages if str(page).strip()] if isinstance(pages, list) else []


def source_file_exists(vault_path: Path, source_file: str) -> bool:
    path = Path(source_file).expanduser()
    if not path.is_absolute():
        path = vault_path / path
    return path.exists()


def has_same_basename(source_file: str, discovered_source_files: set[str]) -> bool:
    basename = Path(source_file).name
    return any(Path(candidate).name == basename and candidate != source_file for candidate in discovered_source_files)


def relative_or_absolute(vault_path: Path, path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(vault_path).as_posix()
    except ValueError:
        return str(resolved)
