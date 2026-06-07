from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
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
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
        try:
            response = search_query(request)
            response.stats["vault_path"] = str(vault_path)
            response.stats.update(_vault_stats(vault_path))
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

    def context(self, request: WikiContextRequest) -> WikiContextResponse:
        return build_wiki_context(request)

    def feedback(self, request: WikiQueryFeedbackRequest) -> WikiQueryFeedbackResponse:
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
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


def _vault_stats(vault_path: Path) -> dict[str, str]:
    try:
        config = load_config(default_config_path())
    except Exception:
        return {}
    resolved = vault_path.expanduser().resolve()
    for vault_id, profile in config.vaults.profiles.items():
        try:
            if profile.path.expanduser().resolve() == resolved:
                return {"vault_id": vault_id, "vault_name": profile.name}
        except OSError:
            continue
    return {}
