"""Semantic contract boundary for prompts, model calls, and structured outputs."""

from knoarbor.semantic.contracts import SemanticContract, load_prompt, load_semantic_contract
from knoarbor.semantic.llm import (
    ChatClient,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamChunk,
    ChatMessage,
    ModelGateway,
    OllamaNativeChatClient,
    OpenAICompatibleChatClient,
    ProviderAdapter,
    ProviderHealthCheck,
    ProviderModelDiscovery,
)
from knoarbor.semantic.lint_workflow import LintSemanticWorkflow
from knoarbor.semantic.factory import build_lint_semantic_workflow, build_semantic_runner
from knoarbor.semantic.runner import (
    SemanticPromptPackage,
    SemanticRetryPolicy,
    SemanticRunResult,
    SemanticRunner,
    build_semantic_prompt_package,
    parse_contract_output,
)

__all__ = [
    "ChatClient",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionStreamChunk",
    "ChatMessage",
    "LintSemanticWorkflow",
    "ModelGateway",
    "OllamaNativeChatClient",
    "OpenAICompatibleChatClient",
    "ProviderAdapter",
    "ProviderHealthCheck",
    "ProviderModelDiscovery",
    "SemanticContract",
    "SemanticPromptPackage",
    "SemanticRetryPolicy",
    "SemanticRunResult",
    "SemanticRunner",
    "build_lint_semantic_workflow",
    "build_semantic_runner",
    "build_semantic_prompt_package",
    "load_prompt",
    "load_semantic_contract",
    "parse_contract_output",
]
