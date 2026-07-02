from __future__ import annotations

from typing import Any

from knoarbor.core.schemas.chat import ChatCitation, ChatSessionRecord, ChatToolTraceItem
from knoarbor.core.schemas.image_generation import ImageGenerationRequest
from knoarbor.services.chat_context import latest_user_text
from knoarbor.services.chat_evidence import CHAT_EVIDENCE_PACK_SCHEMA_VERSION, ChatEvidencePlanner
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.services.chat_generated_images import store_chat_generated_image

def list_vaults(context: ChatToolContext, arguments: dict[str, Any]) -> ChatToolTraceItem:
    response = context.services.vaults.list_vaults(config_path=str(arguments.get("config_path") or context.request.config_path or "").strip() or None)
    vaults = [vault.model_dump() for vault in response.vaults]
    return ChatToolTraceItem(
        tool="list_vaults",
        arguments=arguments,
        summary=f"Listed {len(vaults)} configured vault(s).",
        result={
            "schema_version": response.schema_version,
            "config_path": response.config_path,
            "default_vault_id": response.default_vault_id,
            "vaults": vaults,
        },
    )


def reuse_context(context: ChatToolContext, arguments: dict[str, Any]) -> ChatToolTraceItem:
    if not arguments.get("page_paths"):
        combined = _combined_reusable_trace(context.existing_session, context.evidence_planner)
        if combined is not None:
            return combined
    prior = _latest_reusable_trace(context.existing_session, arguments.get("page_paths"))
    if prior is None:
        return context.query_wiki(_with_default_query(arguments, latest_user_text(context.request.messages)))
    return ChatToolTraceItem(
        tool="reuse_context",
        arguments=arguments,
        summary="Reused prior chat evidence.",
        citations=prior.citations,
        result=prior.result,
    )


def answer_directly(_context: ChatToolContext, arguments: dict[str, Any]) -> ChatToolTraceItem:
    return ChatToolTraceItem(
        tool="answer_directly",
        arguments=arguments,
        summary=str(arguments.get("reason") or "No wiki lookup requested."),
        status="skipped",
        result={
            "evidence_pack": {
                "schema_version": CHAT_EVIDENCE_PACK_SCHEMA_VERSION,
                "kind": "direct_answer",
                "warnings": ["No wiki evidence was requested by the planner."],
            }
        },
    )


def generate_image(context: ChatToolContext, arguments: dict[str, Any]) -> ChatToolTraceItem:
    prompt = _required_text(arguments, "prompt")
    provider = _optional_text(arguments, "provider")
    request = ImageGenerationRequest(
        prompt=prompt,
        negative_prompt=_optional_text(arguments, "negative_prompt"),
        response_format=arguments.get("response_format") if arguments.get("response_format") in {"url", "b64_json"} else None,
        extra_body=arguments.get("extra_body") if isinstance(arguments.get("extra_body"), dict) else {},
    )
    response = context.services.image_generation.generate(request, config_path=context.request.config_path, provider_name=provider)
    images: list[dict[str, object]] = []
    for index, image in enumerate(response.images, start=1):
        src = image.markdown_src()
        if not src:
            continue
        stored = store_chat_generated_image(
            image,
            vault_path=context.request.vault_path,
            session_id=context.request.session_id,
            index=index,
        )
        display_src = stored.src if stored else src
        images.append(
            {
                "index": index,
                "src": display_src,
                "markdown": f"![Generated image {index}]({display_src})",
                "mime_type": image.mime_type,
                "revised_prompt": image.revised_prompt,
                "stored_path": stored.path if stored else None,
                "original_src": stored.original_src if stored else src,
            }
        )
    return ChatToolTraceItem(
        tool="generate_image",
        arguments=arguments,
        summary=f"Generated {len(images)} image(s) with {response.provider}/{response.model}.",
        result={
            "schema_version": response.schema_version,
            "provider": response.provider,
            "model": response.model,
            "prompt": response.prompt,
            "images": images,
            "usage": response.usage,
        },
    )


def _latest_reusable_trace(existing_session: ChatSessionRecord | None, page_paths: object = None) -> ChatToolTraceItem | None:
    if existing_session is None:
        return None
    requested = {str(path) for path in page_paths or [] if str(path).strip()} if isinstance(page_paths, list) else set()
    turn_trace = [item for turn in existing_session.turns for item in turn.tool_trace]
    for item in reversed(turn_trace or existing_session.tool_trace):
        if item.status != "ok":
            continue
        if item.tool not in {"query_wiki", "search_wiki", "reuse_context"}:
            continue
        if not isinstance(item.result.get("evidence_pack"), dict):
            continue
        if requested:
            citation_paths = {citation.path for citation in item.citations if citation.path}
            if not requested.intersection(citation_paths):
                continue
        return item
    return None


def _combined_reusable_trace(existing_session: ChatSessionRecord | None, evidence_planner: ChatEvidencePlanner) -> ChatToolTraceItem | None:
    if existing_session is None:
        return None
    trace_items = [item for turn in existing_session.turns[-6:] for item in turn.tool_trace]
    reusable = [
        item
        for item in trace_items
        if item.status == "ok"
        and (
            (item.tool in {"query_wiki", "reuse_context"} and isinstance(item.result.get("evidence_pack"), dict))
            or item.tool == "read_wiki_page"
        )
    ]
    if not reusable:
        return None
    session_pack = evidence_planner.build_session_pack(reusable)
    if session_pack is None:
        return None
    return ChatToolTraceItem(
        tool="reuse_context",
        arguments={"scope": "recent_session_evidence"},
        summary=f"Reused recent session evidence from {len(reusable)} tool result(s).",
        citations=_unique_citations([citation for item in reusable for citation in item.citations]),
        result={"evidence_pack": session_pack.payload},
    )


def _unique_citations(citations: list[ChatCitation]) -> list[ChatCitation]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ChatCitation] = []
    for citation in citations:
        identity = (citation.kind, citation.vault_id or citation.vault_path or "", citation.path or citation.run_id or "")
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(citation)
    return unique


def _with_default_query(arguments: dict[str, Any], query: str) -> dict[str, Any]:
    output = dict(arguments)
    if not str(output.get("query") or "").strip():
        output["query"] = query
    if output.get("mode") not in {"balanced", "deep", "quick"}:
        output["mode"] = "balanced"
    if "max_results" not in output:
        output["max_results"] = 6
    return output


def _required_text(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        from knoarbor.core.errors import UserInputError

        raise UserInputError(f"Chat tool argument is required: {key}")
    return value


def _optional_text(arguments: dict[str, Any], key: str) -> str | None:
    value = str(arguments.get(key) or "").strip()
    return value or None
