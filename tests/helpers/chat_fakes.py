from __future__ import annotations

import json
from dataclasses import dataclass, field

from knoarbor.core.schemas.image_generation import GeneratedImage, ImageGenerationRequest, ImageGenerationResponse
from knoarbor.core.schemas.vaults import VaultListResponse, VaultProfile
from knoarbor.core.schemas.wiki_query import WikiAnswerScope, WikiAnswerSet, WikiAtomTrace, WikiEvidenceCoverage, WikiSearchResponse, WikiSearchResult
from knoarbor.semantic.llm import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionStreamChunk
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.memory import MemoryService
from knoarbor.services.wiki_pages import WikiPageDetail, WikiPageRelation, WikiPageRelationsResponse, WikiPageSummary, WikiPagesResponse


class FakeChatClient:
    model = "fake-model"

    def __init__(self, outputs: list[dict[str, object]], *, provider: str = "fake") -> None:
        self.provider = provider
        self.outputs = list(outputs)
        self.requests: list[ChatCompletionRequest] = []
        self.failures_before_success: list[Exception] = []

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.requests.append(request)
        if self.failures_before_success:
            raise self.failures_before_success.pop(0)
        if "KnoArbor Chat Tool Planner" in request.messages[0].content or "KnoArbor Chat Tool Planner" in request.messages[0].content:
            if self.outputs and isinstance(self.outputs[0], dict) and "tool_calls" in self.outputs[0]:
                payload = self.outputs.pop(0)
                content = json.dumps(payload, ensure_ascii=False)
                return ChatCompletionResponse(
                    content=content,
                    provider=self.provider,
                    model=self.model,
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )
            user_text = request.messages[-1].content
            mode = "deep" if any(term in user_text for term in ["详细", "对比", "比较", "区别", "架构"]) else "balanced"
            max_results = 8 if mode == "deep" else 6
            content = json.dumps(
                {
                    "tool_calls": [{"name": "query_wiki", "arguments": {"query": user_text, "mode": mode, "max_results": max_results}}],
                    "reason": "default fake tool plan",
                    "confidence": 0.8,
                },
                ensure_ascii=False,
            )
            return ChatCompletionResponse(
                content=content,
                provider=self.provider,
                model=self.model,
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        if not self.outputs:
            raise AssertionError("No fake model output left")
        payload = self.outputs.pop(0)
        if isinstance(payload, str):
            content = payload
        elif request.structured_output is False and "answer" in payload:
            content = str(payload["answer"])
        else:
            content = json.dumps(payload, ensure_ascii=False)
        return ChatCompletionResponse(
            content=content,
            provider=self.provider,
            model=self.model,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def stream(self, request: ChatCompletionRequest):
        response = self.complete(request)
        midpoint = max(1, len(response.content) // 2)
        for delta in (response.content[:midpoint], response.content[midpoint:]):
            if delta:
                yield ChatCompletionStreamChunk(delta=delta)
        yield ChatCompletionStreamChunk(response=response)


class FakeWikiSearch:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return WikiSearchResponse(
            query=request.query,
            retrieval_mode=request.mode,
            results=[
                WikiSearchResult(
                    path="sources/Agent-Loop-Source.md",
                    title="Agent Loop Source",
                    page_role="source",
                    score=12.0,
                    relevance="high",
                    match_kind="direct",
                    reason="source digest match",
                    summary="Source digest for agent loop notes.",
                    content="Source digest content.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                ),
                WikiSearchResult(
                    path="Agent-Loop.md",
                    title="Agent Loop",
                    page_role="primary",
                    score=9.0,
                    relevance="high",
                    match_kind="direct",
                    reason="title match",
                    summary="Agent loop alternates reasoning, action, and observation.",
                    content="Agent Loop full maintained page content.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                    atom_traces=[
                        WikiAtomTrace(
                            atom_id="claim_agent_loop_cycle",
                            atom_type="claim",
                            text="Agent loop alternates reasoning, action, and observation.",
                            source_digest_id="sd_agent_loop",
                        )
                    ],
                ),
                WikiSearchResult(
                    path="Session-Memory-Architecture-for-Agent-Loops.md",
                    title="Session Memory Architecture for Agent Loops",
                    page_role="supporting",
                    score=7.0,
                    relevance="medium",
                    match_kind="related",
                    reason="related implementation page",
                    summary="Session memory explains production support for agent loops.",
                    content="Session memory supporting page content for production agent loops.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                ),
            ],
            primary_pages=[],
            supporting_pages=[],
            source_pages=[],
            answer_scope=WikiAnswerScope(kind="broad", vault_ids=["agent-engineering"], reason="test"),
            answer_set=WikiAnswerSet(
                kind="multi_page",
                primary_paths=["Agent-Loop.md"],
                supporting_paths=["Session-Memory-Architecture-for-Agent-Loops.md"],
                source_paths=["sources/Agent-Loop-Source.md"],
            ),
            evidence_coverage=WikiEvidenceCoverage(status="strong", primary_count=1, supporting_count=1, source_count=1),
            context_pack="Agent Loop context",
            response_guidance=[],
            warnings=[],
        )


class FakeWikiPages:
    def __init__(self) -> None:
        self.read_paths: list[str] = []
        self.list_calls = 0
        self.link_paths: list[str] = []

    def list_pages(self, vault_path, *, vault_id=None, vault_name=None):
        self.list_calls += 1
        return WikiPagesResponse(
            vault_path=str(vault_path),
            vault_id=vault_id,
            vault_name=vault_name,
            pages=[
                WikiPageSummary(
                    path="Agent-Loop.md",
                    directory="pages",
                    title="Agent Loop",
                    summary="Agent loop alternates reasoning, action, and observation.",
                    headings=["Summary", "Control patterns"],
                ),
                WikiPageSummary(
                    path="OpenClaw.md",
                    directory="pages",
                    title="OpenClaw",
                    summary="OpenClaw is an engineering agent platform.",
                    headings=["Summary"],
                ),
            ],
        )

    def read_page(self, vault_path, relative_path, *, vault_id=None, vault_name=None):
        self.read_paths.append(relative_path)
        return WikiPageDetail(
            path=relative_path,
            vault_path=str(vault_path),
            vault_id=vault_id,
            vault_name=vault_name,
            content=f"# {relative_path}\n\nMaintained answer page content.",
            metadata={},
            summary=WikiPageSummary(
                path=relative_path,
                directory=relative_path.split("/", 1)[0],
                title=relative_path.rsplit("/", 1)[-1].removesuffix(".md"),
                summary="Maintained answer page summary.",
            ),
        )

    def page_relations(self, vault_path, relative_path, *, vault_id=None, vault_name=None):
        self.link_paths.append(relative_path)
        return WikiPageRelationsResponse(
            path=relative_path,
            vault_path=str(vault_path),
            vault_id=vault_id,
            vault_name=vault_name,
            outgoing_pages=[
                WikiPageRelation(source=relative_path, target="OpenClaw", target_path="OpenClaw.md", resolved=True),
            ],
            incoming_pages=[
                WikiPageRelation(source="Agent-Engineering.md", target="Agent Loop", target_path=relative_path, resolved=True),
            ],
        )


class FakeVaults:
    def list_vaults(self, *, config_path=None):
        return VaultListResponse(
            config_path=config_path,
            default_vault_id="agent-engineering",
            vaults=[
                VaultProfile(id="agent-engineering", name="Agent Engineering", path="/tmp/vault", active=True, exists=True),
                VaultProfile(id="rag", name="RAG Notes", path="/tmp/rag", active=False, exists=True),
            ],
        )


@dataclass
class FakeImageGeneration:
    requests: list[ImageGenerationRequest] = field(default_factory=list)

    def generate(self, request: ImageGenerationRequest, *, config_path=None, provider_name=None):
        self.requests.append(request)
        return ImageGenerationResponse(
            provider=provider_name or "sensenova",
            model="sensenova-u1-fast",
            prompt=request.prompt,
            images=[GeneratedImage(b64_json="ZmFrZS1wbmc=", mime_type="image/png")],
            usage={"total_tokens": 1},
        )


@dataclass
class FakeServices:
    wiki_search: FakeWikiSearch = field(default_factory=FakeWikiSearch)
    wiki_pages: FakeWikiPages = field(default_factory=FakeWikiPages)
    vaults: FakeVaults = field(default_factory=FakeVaults)
    image_generation: FakeImageGeneration = field(default_factory=FakeImageGeneration)
    memory: MemoryService = field(default_factory=MemoryService)
    chat_sessions: ChatSessionStore = field(default_factory=ChatSessionStore)
