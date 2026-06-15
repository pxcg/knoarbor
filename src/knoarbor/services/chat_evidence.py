from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.wiki_query import WikiSearchResult


@dataclass(frozen=True)
class ChatEvidencePack:
    """Model-facing evidence pack derived from a wiki search result."""

    payload: dict[str, Any]


class ChatEvidencePlanner:
    """Plans model-facing evidence for bounded wiki chat.

    Chat tools may keep rich raw results for UI traces, but the next model turn
    should receive a purpose-built evidence pack instead of a large raw JSON
    observation. This keeps the loop page-first while preserving enough detail
    for grounded answers.
    """

    def build_search_pack(
        self,
        *,
        query: str,
        result_count: int,
        answer_scope: dict[str, Any],
        answer_set: dict[str, Any],
        evidence_coverage: dict[str, Any],
        primary_page: dict[str, Any] | None,
        primary_pages: list[dict[str, Any]],
        supporting_pages: list[dict[str, Any]],
        source_pages: list[dict[str, Any]],
        results: list[dict[str, Any]],
        warnings: list[str],
    ) -> ChatEvidencePack:
        primary_pages = primary_pages or ([primary_page] if primary_page else [])
        action = self._recommended_action(evidence_coverage, primary_page)
        evidence_paths: set[str] = set()
        for page in primary_pages:
            if page and page.get("path"):
                evidence_paths.add(str(page["path"]))
        for page in [*supporting_pages, *source_pages]:
            if page.get("path"):
                evidence_paths.add(str(page["path"]))
        payload = {
            "schema_version": "chat_evidence_pack.v1",
            "kind": "wiki_search_evidence",
            "query": query,
            "result_count": result_count,
            "answer_scope": answer_scope,
            "answer_set": answer_set,
            "synthesis_outline": self._synthesis_outline(answer_scope, primary_page, supporting_pages),
            "evidence_coverage": evidence_coverage,
            "recommended_action": action,
            "primary_page": self._primary_payload(primary_page),
            "primary_pages": [self._primary_payload(page) for page in primary_pages if page],
            "supporting_pages": [self._supporting_payload(page) for page in supporting_pages],
            "source_pages": [self._source_payload(page) for page in source_pages],
            "further_results": [self._result_payload(item) for item in results if item.get("path") not in evidence_paths][:5],
            "warnings": warnings,
            "instructions": self._instructions(action, evidence_coverage, primary_page),
        }
        return ChatEvidencePack(payload=payload)

    def project_tool_observation(self, tool: str, status: str, summary: str, result: dict[str, Any]) -> dict[str, Any]:
        if tool in {"query_wiki", "search_wiki", "reuse_context"} and isinstance(result.get("evidence_pack"), dict):
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "evidence_pack": result["evidence_pack"],
            }
        if tool == "read_wiki_page":
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "page": {
                    "path": result.get("path"),
                    "title": result.get("title"),
                    "summary": result.get("summary"),
                    "content": compact_inline_text(str(result.get("content") or ""), 18000),
                    "truncated": bool(result.get("truncated")),
                },
            }
        return {
            "tool": tool,
            "status": status,
            "summary": summary,
            "result": _compact_value(result, max_chars=12000),
        }

    def _recommended_action(self, evidence_coverage: dict[str, Any], primary_page: dict[str, Any] | None) -> str:
        if not primary_page:
            return "answer_with_gap"
        if evidence_coverage.get("status") == "weak":
            return "answer_with_gap"
        if primary_page.get("content_truncated"):
            return "read_primary_if_detail_needed"
        return "answer_from_evidence"

    def _instructions(
        self,
        action: str,
        evidence_coverage: dict[str, Any],
        primary_page: dict[str, Any] | None,
    ) -> list[str]:
        instructions = [
            "Answer from the evidence pack, using the primary page as the anchor.",
            "Follow synthesis_outline when it is present; it expresses the wiki-first answer structure for the current question.",
            "Use supporting pages as additional maintained wiki pages, not as disposable snippets.",
            "Keep citations aligned with the evidence pages used in the answer.",
        ]
        if action == "answer_with_gap":
            instructions.append("Local evidence is weak or missing; state the gap clearly before giving any tentative answer.")
        if action == "read_primary_if_detail_needed" and primary_page:
            instructions.append(f"If the user needs more detail, call read_wiki_page for {primary_page.get('path')}.")
        if evidence_coverage.get("missing_facets"):
            instructions.append(f"Potential missing facets: {', '.join(str(item) for item in evidence_coverage.get('missing_facets', []))}.")
        return instructions

    def _synthesis_outline(
        self,
        answer_scope: dict[str, Any],
        primary_page: dict[str, Any] | None,
        supporting_pages: list[dict[str, Any]],
    ) -> list[str]:
        if not primary_page:
            return [
                "State the local wiki coverage gap.",
                "If useful, suggest a specific ingest or query refinement action.",
            ]
        if answer_scope.get("kind") == "narrow":
            return [
                "Start with a direct definition or answer from the primary page.",
                "Explain the core mechanism or decision points from that maintained page.",
                "Use supporting pages for extensions, comparisons, implementation details, and missing facets.",
                "End with concise related topics when they help the user continue.",
            ]
        support_types = sorted({str(page.get("type") or "") for page in supporting_pages if page.get("type")})
        outline = [
            "Start with the main thesis from the primary page.",
            "Group supporting pages by the role they play: concepts, implementations, comparisons, workflows, or sources.",
            "Synthesize across pages into a coherent structure instead of listing raw matches.",
            "Call out where source pages provide provenance rather than the main answer.",
        ]
        if support_types:
            outline.append(f"Available supporting page types: {', '.join(support_types)}.")
        return outline

    def _primary_payload(self, page: dict[str, Any] | None) -> dict[str, Any] | None:
        if not page:
            return None
        return {
            "path": page.get("path"),
            "title": page.get("title"),
            "type": page.get("type"),
            "score": page.get("score"),
            "relevance": page.get("relevance"),
            "summary": page.get("summary"),
            "key_points": page.get("key_points", []),
            "content": compact_inline_text(str(page.get("content") or ""), 22000),
            "content_truncated": bool(page.get("content_truncated")),
            "vault_id": page.get("vault_id"),
            "vault_name": page.get("vault_name"),
        }

    def _supporting_payload(self, page: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": page.get("path"),
            "title": page.get("title"),
            "type": page.get("type"),
            "role": page.get("role"),
            "score": page.get("score"),
            "relevance": page.get("relevance"),
            "summary": page.get("summary"),
            "key_points": page.get("key_points", []),
            "content": compact_inline_text(str(page.get("content") or ""), 18000),
            "content_truncated": bool(page.get("content_truncated")),
            "vault_id": page.get("vault_id"),
            "vault_name": page.get("vault_name"),
        }

    def _source_payload(self, page: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": page.get("path"),
            "title": page.get("title"),
            "summary": page.get("summary"),
            "vault_id": page.get("vault_id"),
            "vault_name": page.get("vault_name"),
        }

    def _result_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": item.get("path"),
            "title": item.get("title"),
            "type": item.get("type"),
            "role": item.get("role"),
            "score": item.get("score"),
            "summary": item.get("summary"),
            "vault_id": item.get("vault_id"),
            "vault_name": item.get("vault_name"),
        }


def search_result_to_chat_payload(item: WikiSearchResult) -> dict[str, Any]:
    return {
        "path": item.path,
        "title": item.title,
        "type": item.type,
        "role": item.role,
        "score": item.score,
        "summary": item.summary,
        "key_points": item.key_points[:5],
        "vault_id": item.vault_id,
        "vault_name": item.vault_name,
        "is_primary": item.role == "primary",
    }


def _compact_value(value: Any, *, max_chars: int) -> Any:
    text = str(value)
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "preview": compact_inline_text(text, max_chars)}
