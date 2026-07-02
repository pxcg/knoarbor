from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from knoarbor.core.schemas.chat import ChatRequest, ChatSessionRecord, ChatToolPlan, ChatToolTraceItem
from knoarbor.services.chat_evidence import ChatEvidencePlanner
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.services.chat_tool_handlers import answer_directly, generate_image, list_vaults, reuse_context
from knoarbor.services.chat_tool_registry import ChatToolRegistry
from knoarbor.services.chat_wiki_tools import inspect_wiki_relations, list_wiki_pages, query_wiki, read_wiki_page, with_default_query

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


ChatToolEventCallback = Callable[[str, str, str | None, int | None, str | None], None]


@dataclass
class ChatToolExecutor:
    """Executes KnoArbor-owned chat tools.

    This layer owns tool dispatch and event reporting. Individual tool modules
    own payload assembly and domain-specific behavior.
    """

    request: ChatRequest
    services: ApplicationServices
    existing_session: ChatSessionRecord | None = None
    event_callback: ChatToolEventCallback | None = None
    evidence_planner: ChatEvidencePlanner = field(default_factory=ChatEvidencePlanner)

    def execute(self, plan: ChatToolPlan, query: str) -> list[ChatToolTraceItem]:
        context = ChatToolContext(
            request=self.request,
            services=self.services,
            existing_session=self.existing_session,
            evidence_planner=self.evidence_planner,
            query_wiki=lambda arguments: query_wiki(context, arguments),
        )
        registry = self._registry()
        observations: list[ChatToolTraceItem] = []
        for index, call in enumerate(plan.tool_calls[:4], start=1):
            tool_name = call.name
            self._event("tool_call_started", f"Running chat tool: {tool_name}.", tool_name, index, None)
            try:
                arguments = self._prepare_arguments(tool_name, call.arguments, query)
                observation = registry.execute(context, tool_name, arguments)
            except Exception as exc:  # noqa: BLE001 - tool failures become model-visible observations.
                observation = ChatToolTraceItem(
                    tool=tool_name,
                    arguments=call.arguments,
                    status="error",
                    summary=f"Tool failed: {exc}",
                    result={"error": str(exc)},
                )
            observations.append(observation)
            self._event(
                "tool_call_failed" if observation.status == "error" else "tool_call_finished",
                observation.summary,
                observation.tool,
                index,
                observation.status,
            )
        if not observations:
            observations.append(query_wiki(context, {"query": query, "mode": "balanced", "max_results": 6}))
        return observations

    def _registry(self) -> ChatToolRegistry:
        return ChatToolRegistry(
            handlers={
                "query_wiki": query_wiki,
                "list_wiki_pages": list_wiki_pages,
                "read_wiki_page": read_wiki_page,
                "inspect_wiki_relations": inspect_wiki_relations,
                "list_vaults": list_vaults,
                "reuse_context": reuse_context,
                "generate_image": generate_image,
                "answer_directly": answer_directly,
                "finish_answer": answer_directly,
            },
            fallback_handler=answer_directly,
        )

    def _prepare_arguments(self, tool_name: str, arguments: dict, query: str) -> dict:
        if tool_name == "query_wiki":
            return with_default_query(arguments, query)
        if tool_name == "generate_image":
            return _with_default_prompt(arguments, query)
        return arguments

    def _event(self, event_type: str, message: str, tool: str | None, turn: int | None, status: str | None) -> None:
        if self.event_callback:
            self.event_callback(event_type, message, tool, turn, status)


def _with_default_prompt(arguments: dict, query: str) -> dict:
    output = dict(arguments)
    if not str(output.get("prompt") or "").strip():
        output["prompt"] = query
    return output
