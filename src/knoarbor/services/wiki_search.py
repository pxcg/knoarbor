from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.vaults import resolve_config_vault_path
from knoarbor.core.schemas.wiki_query import (
    WikiContextRequest,
    WikiContextResponse,
    WikiQueryFeedbackRequest,
    WikiQueryFeedbackResponse,
    WikiQueryTrendResponse,
    WikiSearchRequest,
    WikiSearchResponse,
)
from knoarbor.audit.query_ledger import append_query_feedback, append_query_record, build_query_trend
from knoarbor.audit.query_report import write_query_report
from knoarbor.audit.run_failure import write_run_failure_artifacts
from knoarbor.presenters.wiki_context import build_wiki_context, search_query
from knoarbor.runtime import current_run_monitor, runtime_logger

logger = runtime_logger(__name__)


class WikiSearchService:
    """Retrieves compact wiki context for Hermes or other query callers."""

    def search(self, request: WikiSearchRequest) -> WikiSearchResponse:
        if request.all_vaults or request.vault_ids:
            return self._search_many(request)
        return self._search_one(request)

    def _search_one(self, request: WikiSearchRequest) -> WikiSearchResponse:
        request, vault_path = _resolve_query_request(request)
        try:
            response = search_query(request)
            response.stats["vault_path"] = str(vault_path)
            response.stats.update(_vault_stats(vault_path, config_path=request.config_path, vault_id=request.vault_id))
            _annotate_results_with_vault(response, vault_path)
            response.stats["query_trend"] = build_query_trend(vault_path)
            if request.record_query:
                ledger_path = append_query_record(vault_path, request, response)
                response.stats["query_ledger_path"] = str(ledger_path)
            if request.write_report:
                response.stats["query_report_path"] = write_query_report(vault_path, request, response)
            return response
        except Exception as exc:
            self._write_failure_artifacts(vault_path, request, exc)
            raise

    def _search_many(self, request: WikiSearchRequest) -> WikiSearchResponse:
        config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
        target_vault_ids = list(config.vaults.profiles) if request.all_vaults else _unique_nonempty(request.vault_ids)
        if not target_vault_ids:
            raise UserInputError("No vault_ids were provided and no configured vault profiles are available.")

        responses: list[WikiSearchResponse] = []
        warnings: list[str] = []
        for vault_id in target_vault_ids:
            if vault_id not in config.vaults.profiles:
                known = ", ".join(sorted(config.vaults.profiles)) or "none"
                raise UserInputError(f"Unknown vault_id: {vault_id}. Known vaults: {known}")
            scoped_request = request.model_copy(
                update={
                    "obsidian_vault_path": None,
                    "vault_id": vault_id,
                    "vault_ids": [],
                    "all_vaults": False,
                },
            )
            response = self._search_one(scoped_request)
            responses.append(response)
            warnings.extend(response.warnings)

        merged_results = sorted(
            [result for response in responses for result in response.results],
            key=lambda item: item.score,
            reverse=True,
        )[: request.max_results]
        context_pack = _merge_context_packs(responses)
        return WikiSearchResponse(
            query=request.query,
            retrieval_mode=request.mode,
            results=merged_results,
            context_pack=context_pack,
            answer_guidance=_merge_unique([item for response in responses for item in response.answer_guidance]),
            gap_suggestions=[item for response in responses for item in response.gap_suggestions],
            gaps=_merge_unique([item for response in responses for item in response.gaps]),
            warnings=_merge_unique(warnings),
            stats={
                "multi_vault": True,
                "vault_count": len(responses),
                "vault_ids": target_vault_ids,
                "result_count": len(merged_results),
                "context_pack_chars": len(context_pack),
                "per_vault": [
                    {
                        "vault_id": response.stats.get("vault_id"),
                        "vault_name": response.stats.get("vault_name"),
                        "vault_path": response.stats.get("vault_path"),
                        "result_count": len(response.results),
                    }
                    for response in responses
                ],
            },
            trace={"vault_ids": target_vault_ids},
        )

    def context(self, request: WikiContextRequest) -> WikiContextResponse:
        return build_wiki_context(request)

    def feedback(self, request: WikiQueryFeedbackRequest) -> WikiQueryFeedbackResponse:
        request, vault_path = _resolve_feedback_request(request)
        if not vault_path.exists() or not vault_path.is_dir():
            raise UserInputError(f"obsidian_vault_path does not exist or is not a directory: {vault_path}")
        ledger_path = append_query_feedback(vault_path, request)
        return WikiQueryFeedbackResponse(recorded=True, ledger_path=str(ledger_path))

    def trend(self, vault_path: str, *, limit: int = 100) -> WikiQueryTrendResponse:
        path = Path(vault_path).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise UserInputError(f"obsidian_vault_path does not exist or is not a directory: {path}")
        return WikiQueryTrendResponse(**build_query_trend(path, limit=limit))

    def _write_failure_artifacts(self, vault_path: Path, request: WikiSearchRequest, exc: BaseException) -> None:
        if not request.write_report and not request.record_query:
            return
        if not vault_path.exists() or not vault_path.is_dir():
            logger.info("query_failure_report_skipped reason=no_vault_path vault=%s error=%s", vault_path, exc)
            return
        try:
            monitor = current_run_monitor()
            write_run_failure_artifacts(
                vault_path,
                flow="query",
                request=request,
                exc=exc,
                run_id=monitor.run_id if monitor else None,
                stage=monitor.read().stage if monitor else None,
                append_ledger=request.record_query,
                write_report=request.write_report,
            )
        except Exception as report_exc:
            logger.exception("query_failure_report_write_failed error=%s original_error=%s", report_exc, exc)


def _vault_stats(vault_path: Path, *, config_path: str | None = None, vault_id: str | None = None) -> dict[str, str]:
    try:
        config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
    except Exception:
        return {}
    resolved = vault_path.expanduser().resolve()
    for profile_id, profile in config.vaults.profiles.items():
        try:
            if profile.path.expanduser().resolve() == resolved:
                return {"vault_id": profile_id, "vault_name": profile.name}
        except OSError:
            continue
    if vault_id:
        return {"vault_id": vault_id}
    return {}


def _annotate_results_with_vault(response: WikiSearchResponse, vault_path: Path) -> None:
    vault_id = response.stats.get("vault_id")
    vault_name = response.stats.get("vault_name")
    for index, result in enumerate(response.results):
        response.results[index] = result.model_copy(
            update={
                "vault_id": str(vault_id) if vault_id else None,
                "vault_name": str(vault_name) if vault_name else None,
                "vault_path": str(vault_path),
            },
        )


def _merge_context_packs(responses: list[WikiSearchResponse]) -> str:
    sections: list[str] = []
    for response in responses:
        context_pack = response.context_pack.strip()
        if not context_pack:
            continue
        vault_label = response.stats.get("vault_name") or response.stats.get("vault_id") or response.stats.get("vault_path") or "unknown"
        sections.append(f"# {vault_label}\n\n{context_pack}")
    return "\n\n---\n\n".join(sections)


def _merge_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _unique_nonempty(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _resolve_query_request(request: WikiSearchRequest) -> tuple[WikiSearchRequest, Path]:
    config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
    vault_path = resolve_config_vault_path(config, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
    return request.model_copy(update={"obsidian_vault_path": str(vault_path), "vault_id": request.vault_id or _vault_id_for_path(config, vault_path)}), vault_path


def _resolve_feedback_request(request: WikiQueryFeedbackRequest) -> tuple[WikiQueryFeedbackRequest, Path]:
    config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
    vault_path = resolve_config_vault_path(config, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
    return request.model_copy(update={"obsidian_vault_path": str(vault_path), "vault_id": request.vault_id or _vault_id_for_path(config, vault_path)}), vault_path


def _vault_id_for_path(config, vault_path: Path) -> str | None:
    resolved = vault_path.expanduser().resolve()
    for vault_id, profile in config.vaults.profiles.items():
        try:
            if profile.path.expanduser().resolve() == resolved:
                return vault_id
        except OSError:
            continue
    return None
