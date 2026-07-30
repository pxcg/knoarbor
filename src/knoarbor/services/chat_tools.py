from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from knoarbor.core.schemas.chat import ChatRequest, ChatToolPlan, ChatToolTraceItem
from knoarbor.services.chat_knowledge_tools import retrieve_knowledge_batch
from knoarbor.services.chat_dependencies import ChatToolDependencies
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.services.chat_tool_handlers import generate_image, list_vaults
from knoarbor.services.chat_tool_registry import ChatToolRegistry
from knoarbor.services.chat_execution_safety import ChatExecutionSafetyExceeded
from knoarbor.runtime.run_monitor import RunCancelled

ChatToolEventCallback = Callable[[str, str, str | None, int | None, str | None], None]


@dataclass
class ChatToolExecutor:
    """Executes product-owned chat tools.

    This layer owns tool dispatch and event reporting. Individual tool modules
    own payload assembly and domain-specific behavior.
    """

    request: ChatRequest
    services: ChatToolDependencies
    event_callback: ChatToolEventCallback | None = None
    raise_if_stopped: Callable[[], None] | None = None
    before_tool_call: Callable[[], None] | None = None
    observe_tool_result: Callable[[dict[str, object]], None] | None = None
    _tool_registry: ChatToolRegistry | None = field(default=None, init=False, repr=False)

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._registry().handlers

    def execute(self, plan: ChatToolPlan, query: str) -> list[ChatToolTraceItem]:
        context = ChatToolContext(
            request=self.request,
            services=self.services,
            raise_if_cancelled=self.raise_if_stopped,
        )
        registry = self._registry()
        observations: list[ChatToolTraceItem] = []
        for index, call in enumerate(plan.tool_calls[:1], start=1):
            if self.raise_if_stopped is not None:
                self.raise_if_stopped()
            if self.before_tool_call is not None:
                self.before_tool_call()
            tool_name = call.name
            self._event("tool_call_started", f"Running chat tool: {tool_name}.", tool_name, index, None)
            try:
                arguments = self._prepare_arguments(tool_name, call.arguments, query)
                observation = registry.execute(context, tool_name, arguments)
                if self.observe_tool_result is not None:
                    self.observe_tool_result(observation.result)
                if self.raise_if_stopped is not None:
                    self.raise_if_stopped()
            except (RunCancelled, ChatExecutionSafetyExceeded):
                raise
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
        return observations

    def _registry(self) -> ChatToolRegistry:
        if self._tool_registry is not None:
            return self._tool_registry
        handlers = {
            "retrieve_knowledge_batch": retrieve_knowledge_batch,
            "list_vaults": list_vaults,
        }
        if self.services.image_generation.is_available(self.request.config_path):
            handlers["generate_image"] = generate_image
        self._tool_registry = ChatToolRegistry(
            handlers=handlers,
        )
        return self._tool_registry

    def _prepare_arguments(self, tool_name: str, arguments: dict, query: str) -> dict:
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
