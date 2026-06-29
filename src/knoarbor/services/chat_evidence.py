from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.chat import ChatToolTraceItem
from knoarbor.core.schemas.wiki_query import WikiSearchResult


CHAT_EVIDENCE_PACK_SCHEMA_VERSION = "chat_evidence_pack.v1"

CHAT_EVIDENCE_PACK_KEYS = (
    "kind",
    "query",
    "answer_scope",
    "answer_set",
    "evidence_coverage",
    "primary_pages",
    "supporting_pages",
    "source_pages",
    "citation_pages",
    "further_results",
)


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
        answer_type = _infer_answer_type(query=query, answer_scope=answer_scope)
        action = self._recommended_action(evidence_coverage, primary_page)
        evidence_paths: set[str] = set()
        for page in primary_pages:
            if page and page.get("path"):
                evidence_paths.add(str(page["path"]))
        for page in [*supporting_pages, *source_pages]:
            if page.get("path"):
                evidence_paths.add(str(page["path"]))
        payload = {
            "schema_version": CHAT_EVIDENCE_PACK_SCHEMA_VERSION,
            "kind": "wiki_search_evidence",
            "query": query,
            "result_count": result_count,
            "answer_type": answer_type,
            "answer_scope": answer_scope,
            "answer_set": answer_set,
            "evidence_policy": self._evidence_policy(answer_type, evidence_coverage, primary_pages, supporting_pages, source_pages),
            "synthesis_outline": self._synthesis_outline(answer_scope, primary_page, supporting_pages, answer_type=answer_type),
            "evidence_coverage": evidence_coverage,
            "recommended_action": action,
            "primary_page": self._primary_payload(primary_page, answer_type=answer_type, index=0),
            "primary_pages": [self._primary_payload(page, answer_type=answer_type, index=index) for index, page in enumerate(primary_pages) if page],
            "supporting_pages": [self._supporting_payload(page, answer_type=answer_type, index=index) for index, page in enumerate(supporting_pages)],
            "source_pages": [self._source_payload(page, answer_type=answer_type, index=index) for index, page in enumerate(source_pages)],
            "citation_pages": _citation_pages(primary_pages, supporting_pages, source_pages),
            "further_results": [self._result_payload(item) for item in results if item.get("path") not in evidence_paths][:5],
            "warnings": warnings,
            "instructions": self._instructions(action, evidence_coverage, primary_page, answer_type=answer_type),
        }
        return ChatEvidencePack(payload=payload)

    def build_session_pack(self, observations: list[ChatToolTraceItem]) -> ChatEvidencePack | None:
        primary_pages: list[dict[str, Any]] = []
        supporting_pages: list[dict[str, Any]] = []
        source_pages: list[dict[str, Any]] = []
        queries: list[str] = []
        for item in observations:
            if item.tool == "read_wiki_page":
                page_payload = {
                    "path": item.result.get("path"),
                    "title": item.result.get("title"),
                    "type": str(item.result.get("path") or "").split("/", 1)[0].removesuffix("s"),
                    "role": "primary",
                    "score": None,
                    "relevance": "high",
                    "summary": item.result.get("summary"),
                    "claims": [],
                    "content": item.result.get("content") or "",
                    "content_truncated": item.result.get("truncated", False),
                    "vault_id": item.result.get("vault_id"),
                    "vault_name": item.result.get("vault_name"),
                }
                if page_payload["path"]:
                    primary_pages.append(page_payload)
                continue
            pack = item.result.get("evidence_pack")
            if not isinstance(pack, dict):
                continue
            if pack.get("query"):
                queries.append(str(pack["query"]))
            primary_pages.extend(_pack_pages(pack, "primary_pages"))
            primary_page = pack.get("primary_page")
            if isinstance(primary_page, dict):
                primary_pages.append(primary_page)
            supporting_pages.extend(_pack_pages(pack, "supporting_pages"))
            source_pages.extend(_pack_pages(pack, "source_pages"))
        primary_pages = _unique_pages(primary_pages)
        primary_paths = {page.get("path") for page in primary_pages}
        supporting_pages = _unique_pages([page for page in supporting_pages if page.get("path") not in primary_paths])
        source_pages = _unique_pages(source_pages)
        if not primary_pages and not supporting_pages:
            return None
        answer_paths = [str(page["path"]) for page in primary_pages if page.get("path")]
        supporting_paths = [str(page["path"]) for page in supporting_pages if page.get("path")]
        source_paths = [str(page["path"]) for page in source_pages if page.get("path")]
        payload = {
            "schema_version": CHAT_EVIDENCE_PACK_SCHEMA_VERSION,
            "kind": "session_evidence",
            "query": " / ".join(_unique_strings(queries[-4:])) or "prior session evidence",
            "result_count": len(primary_pages) + len(supporting_pages) + len(source_pages),
            "answer_type": "synthesis",
            "answer_scope": {
                "kind": "broad",
                "vault_ids": _unique_strings([str(page.get("vault_id")) for page in [*primary_pages, *supporting_pages] if page.get("vault_id")]),
                "reason": "Aggregated from recent chat evidence.",
            },
            "answer_set": {
                "kind": "multi_page" if len(answer_paths) + len(supporting_paths) > 1 else "single_page",
                "primary_paths": answer_paths,
                "supporting_paths": supporting_paths,
                "source_paths": source_paths,
                "reason": "Recent chat evidence reused for a follow-up synthesis request.",
                "stop_reason": "session_context",
            },
            "evidence_policy": {
                "answer_contract": "Synthesize the prior maintained wiki pages into the requested artifact.",
                "primary_role": "Use primary pages as the main claims and architecture anchors.",
                "supporting_role": "Use supporting pages to fill mechanisms, tradeoffs, examples, and implementation details.",
                "source_role": "Use source pages only for provenance unless the user asks about origins.",
                "citation_policy": "Cite only pages that directly support the written answer; do not cite every reused page.",
            },
            "synthesis_outline": [
                "Answer from the maintained pages already used in this chat session.",
                "Synthesize across recent evidence instead of starting a new broad search.",
                "Use source pages only as provenance unless the user asks about sources.",
            ],
            "evidence_coverage": {
                "status": "strong" if primary_pages else "adequate",
                "primary_count": len(primary_pages),
                "supporting_count": len(supporting_pages),
                "source_count": len(source_pages),
                "gap_count": 0,
            },
            "recommended_action": "answer_from_evidence",
            "primary_page": _with_role_rationale(primary_pages[0], "primary", "synthesis", 0) if primary_pages else None,
            "primary_pages": [_with_role_rationale(page, "primary", "synthesis", index) for index, page in enumerate(primary_pages)],
            "supporting_pages": [_with_role_rationale(page, "supporting", "synthesis", index) for index, page in enumerate(supporting_pages)],
            "source_pages": [_with_role_rationale(page, "source", "synthesis", index) for index, page in enumerate(source_pages)],
            "citation_pages": _citation_pages(primary_pages, supporting_pages, source_pages),
            "further_results": [],
            "warnings": [],
            "instructions": [
                "This pack aggregates prior session evidence for a direct follow-up.",
                "Use it to summarize, reorganize, compare, or produce a design artifact from prior discussion.",
            ],
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
        if tool == "list_wiki_pages":
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "pages": [
                    {
                        "path": page.get("path"),
                        "title": page.get("title"),
                        "type": page.get("type"),
                        "summary": page.get("summary"),
                        "vault_id": page.get("vault_id"),
                        "vault_name": page.get("vault_name"),
                    }
                    for page in result.get("pages", [])
                    if isinstance(page, dict)
                ][:80],
                "total_pages": result.get("total_pages"),
                "returned_pages": result.get("returned_pages"),
            }
        if tool == "inspect_wiki_relations":
            return {
                "tool": tool,
                "status": status,
                "summary": summary,
                "path": result.get("path"),
                "outgoing_pages": result.get("outgoing_pages", []),
                "incoming_pages": result.get("incoming_pages", []),
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
                "images": [
                    {
                        "index": image.get("index"),
                        "markdown": image.get("markdown"),
                        "mime_type": image.get("mime_type"),
                        "revised_prompt": image.get("revised_prompt"),
                    }
                    for image in result.get("images", [])
                    if isinstance(image, dict)
                ],
                "usage": result.get("usage", {}),
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
        *,
        answer_type: str,
    ) -> list[str]:
        instructions = [
            "Answer from the evidence pack, using the primary page as the anchor.",
            "Follow synthesis_outline when it is present; it expresses the wiki-first answer structure for the current question.",
            f"Use answer_type={answer_type} to choose the answer shape and evidence depth.",
            "Use supporting pages as additional maintained wiki pages, not as disposable snippets.",
            "Keep citations aligned with the evidence pages used in the answer.",
        ]
        if action == "answer_with_gap":
            instructions.append("Local evidence is weak or missing; state the gap clearly before giving any tentative answer.")
        if action == "read_primary_if_detail_needed" and primary_page:
            instructions.append(f"If the user needs more detail, call read_wiki_page for {primary_page.get('path')}.")
        if evidence_coverage.get("missing_dimensions"):
            instructions.append(f"Potential missing evidence dimensions: {', '.join(str(item) for item in evidence_coverage.get('missing_dimensions', []))}.")
        return instructions

    def _synthesis_outline(
        self,
        answer_scope: dict[str, Any],
        primary_page: dict[str, Any] | None,
        supporting_pages: list[dict[str, Any]],
        *,
        answer_type: str,
    ) -> list[str]:
        if not primary_page:
            return [
                "State the local wiki coverage gap.",
                "If useful, suggest a specific ingest or query refinement action.",
            ]
        if answer_type == "comparison":
            return [
                "Start with the central distinction between the compared objects.",
                "Use a compact comparison table when it clarifies decision criteria.",
                "Use primary pages for the main concepts and supporting pages for tradeoffs, examples, and implementation details.",
                "Do not answer as two separate page summaries; synthesize the contrast directly.",
            ]
        if answer_type == "architecture":
            return [
                "Start with the architecture thesis and the system boundary.",
                "Organize by layers, modules, or workflow stages rather than page order.",
                "Use multiple primary/supporting pages as maintained wiki knowledge objects.",
                "Call out responsibilities, interfaces, and tradeoffs when evidence supports them.",
            ]
        if answer_type == "entity_analysis":
            return [
                "Use the entity or comparison page as the case anchor.",
                "Separate reusable patterns from project-specific redesign needs.",
                "Tie the case back to the user's current architecture goal.",
                "Use source pages as provenance for claims about the entity.",
            ]
        if answer_type == "synthesis":
            return [
                "Reuse prior session evidence as the main material.",
                "Produce the requested artifact directly, such as an outline, roadmap, or design section.",
                "Preserve the session's project identity and avoid generic placeholders.",
                "Cite only the core pages that support the synthesized artifact.",
            ]
        if answer_scope.get("kind") == "narrow":
            return [
                "Start with a direct definition or answer from the primary page.",
                "Explain the core mechanism or decision points from that maintained page.",
                "Use supporting pages for extensions, comparisons, implementation details, and missing evidence dimensions.",
                "End with concise related topics when they help the user continue.",
            ]
        outline = [
            "Start with the main thesis from the primary page.",
            "Group supporting pages by their evidence role: background, implementation detail, comparison, source provenance, or follow-up material.",
            "Synthesize across pages into a coherent structure instead of listing raw matches.",
            "Call out where source pages provide provenance rather than the main answer.",
        ]
        return outline

    def _evidence_policy(
        self,
        answer_type: str,
        evidence_coverage: dict[str, Any],
        primary_pages: list[dict[str, Any]],
        supporting_pages: list[dict[str, Any]],
        source_pages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        policy_by_type = {
            "definition": "Define the concept first, then explain mechanism and significance from the maintained page.",
            "comparison": "Compare by decision criteria and boundaries; do not summarize each object separately.",
            "architecture": "Build a layered design from multiple maintained pages and keep module responsibilities explicit.",
            "entity_analysis": "Use the named entity as a reference implementation and separate reusable patterns from redesign needs.",
            "synthesis": "Transform prior evidence into the requested artifact while preserving the session goal.",
            "exploratory": "Answer from the strongest maintained pages and state evidence gaps when coverage is weak.",
        }
        return {
            "answer_contract": policy_by_type.get(answer_type, policy_by_type["exploratory"]),
            "primary_role": f"Use {len(primary_pages)} primary page(s) as the main answer material.",
            "supporting_role": f"Use {len(supporting_pages)} supporting page(s) for mechanisms, comparisons, caveats, and implementation details.",
            "source_role": f"Use {len(source_pages)} source page(s) mainly for provenance and raw-source traceability.",
            "citation_policy": "Public citations should match pages that directly support written claims; do not expose every related page as a citation.",
            "coverage_status": evidence_coverage.get("status", "unknown"),
        }

    def _primary_payload(self, page: dict[str, Any] | None, *, answer_type: str, index: int) -> dict[str, Any] | None:
        if not page:
            return None
        payload = {
            "path": page.get("path"),
            "title": page.get("title"),
            "type": page.get("type"),
            "role": "primary",
            "role_rationale": _role_rationale(page, "primary", answer_type, index),
            "score": page.get("score"),
            "relevance": page.get("relevance"),
            "summary": page.get("summary"),
            "claims": page.get("claims", []),
            "content": compact_inline_text(str(page.get("content") or ""), 22000),
            "content_truncated": bool(page.get("content_truncated")),
            "vault_id": page.get("vault_id"),
            "vault_name": page.get("vault_name"),
            "atom_traces": _atom_traces(page),
        }
        return payload

    def _supporting_payload(self, page: dict[str, Any], *, answer_type: str, index: int) -> dict[str, Any]:
        return {
            "path": page.get("path"),
            "title": page.get("title"),
            "type": page.get("type"),
            "role": page.get("role"),
            "role_rationale": _role_rationale(page, "supporting", answer_type, index),
            "score": page.get("score"),
            "relevance": page.get("relevance"),
            "summary": page.get("summary"),
            "claims": page.get("claims", []),
            "content": compact_inline_text(str(page.get("content") or ""), 18000),
            "content_truncated": bool(page.get("content_truncated")),
            "vault_id": page.get("vault_id"),
            "vault_name": page.get("vault_name"),
            "atom_traces": _atom_traces(page),
        }

    def _source_payload(self, page: dict[str, Any], *, answer_type: str, index: int) -> dict[str, Any]:
        return {
            "path": page.get("path"),
            "title": page.get("title"),
            "type": page.get("type") or "source",
            "role": "source",
            "role_rationale": _role_rationale(page, "source", answer_type, index),
            "summary": page.get("summary"),
            "vault_id": page.get("vault_id"),
            "vault_name": page.get("vault_name"),
            "atom_traces": _atom_traces(page),
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
            "reason": item.get("reason"),
            "atom_traces": _atom_traces(item),
        }


def search_result_to_chat_payload(item: WikiSearchResult) -> dict[str, Any]:
    return {
        "path": item.path,
        "title": item.title,
        "role": item.role,
        "score": item.score,
        "summary": item.summary,
        "claims": item.claims[:5],
        "vault_id": item.vault_id,
        "vault_name": item.vault_name,
        "atom_traces": [trace.model_dump() for trace in item.atom_traces],
        "is_primary": item.role == "primary",
    }


def _pack_pages(pack: dict[str, Any], key: str) -> list[dict[str, Any]]:
    pages = pack.get(key)
    return [page for page in pages if isinstance(page, dict) and page.get("path")] if isinstance(pages, list) else []


def _unique_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for page in pages:
        path = str(page.get("path") or "")
        if not path:
            continue
        identity = (str(page.get("vault_id") or ""), path)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(page)
    return unique


def _citation_pages(
    primary_pages: list[dict[str, Any]],
    supporting_pages: list[dict[str, Any]],
    source_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for role, group in (("primary", primary_pages), ("supporting", supporting_pages), ("source", source_pages)):
        for page in group:
            if not page.get("path"):
                continue
            pages.append(
                {
                    "index": len(pages) + 1,
                    "role": role,
                    "path": page.get("path"),
                    "title": page.get("title"),
                    "vault_id": page.get("vault_id"),
                    "vault_name": page.get("vault_name"),
                    "vault_path": page.get("vault_path"),
                    "reason": page.get("summary") or page.get("reason") or "",
                    "role_rationale": page.get("role_rationale") or _role_rationale(page, role, "exploratory", len(pages)),
                    "atom_traces": _atom_traces(page),
                }
            )
    return _unique_pages(pages)


def _atom_traces(page: dict[str, Any]) -> list[dict[str, Any]]:
    traces = page.get("atom_traces")
    if not isinstance(traces, list):
        return []
    return [trace for trace in traces if isinstance(trace, dict) and trace.get("atom_id")]


def _infer_answer_type(*, query: str, answer_scope: dict[str, Any]) -> str:
    text = query.lower()
    original = query
    if any(term in original for term in ("整理成", "大纲", "方案", "路线图", "总结前面", "前面内容", "文档")) or any(term in text for term in ("outline", "roadmap", "proposal", "synthesize")):
        return "synthesis"
    if any(term in original for term in ("架构", "生产级", "系统设计", "工程模块", "怎么设计", "设计一个")) or any(term in text for term in ("architecture", "production", "system design", "design")):
        return "architecture"
    if any(term in original for term in ("区别", "对比", "关系", "相比", " vs ", "VS")) or any(term in text for term in ("difference", "compare", "versus", " vs ")):
        return "comparison"
    if any(term in original for term in ("参考", "借鉴", "OpenClaw", "Claude Code", "WeKnora")):
        return "entity_analysis"
    if any(term in original for term in ("是什么", "什么是", "定义", "角色")) or any(term in text for term in ("what is", "definition", "role")):
        return "definition"
    if answer_scope.get("kind") == "broad":
        return "architecture"
    return "exploratory"


def _role_rationale(page: dict[str, Any], role: str, answer_type: str, index: int) -> str:
    title = str(page.get("title") or page.get("path") or "page")
    if role == "primary":
        if answer_type == "definition":
            return f"Primary answer anchor for defining {title}."
        if answer_type == "comparison":
            return "Primary comparison material for the user's requested distinction."
        if answer_type == "architecture":
            return "Primary architecture material for layer, module, or workflow design."
        if answer_type == "entity_analysis":
            return "Primary case material for the named entity or reference implementation."
        if answer_type == "synthesis":
            return "Primary prior evidence for the synthesized artifact."
        return "Primary maintained wiki page for the answer."
    if role == "supporting":
        return "Supporting maintained page for mechanisms, caveats, adjacent concepts, or implementation details."
    if role == "source":
        return "Source page for provenance and raw-source traceability; use as a citation only when provenance matters."
    return f"Related page ranked at position {index + 1}."


def _with_role_rationale(page: dict[str, Any], role: str, answer_type: str, index: int) -> dict[str, Any]:
    output = dict(page)
    output["role"] = role
    output["role_rationale"] = _role_rationale(output, role, answer_type, index)
    return output


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _compact_value(value: Any, *, max_chars: int) -> Any:
    text = str(value)
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "preview": compact_inline_text(text, max_chars)}
