from __future__ import annotations

import json
from dataclasses import dataclass, field

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.core.schemas.image_generation import GeneratedImage, ImageGenerationRequest, ImageGenerationResponse
from knoarbor.core.schemas.vaults import VaultListResponse, VaultProfile
from knoarbor.core.schemas.wiki_query import WikiAtomTrace, WikiSearchResponse, WikiSearchResult
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
        self._pending_answer_fixture: dict[str, object] | None = None

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.requests.append(request)
        if self.failures_before_success:
            raise self.failures_before_success.pop(0)
        if (
            "retrieval planner" in request.messages[0].content
            or "Chat Tool Planner" in request.messages[0].content
            or "corpus navigator" in request.messages[0].content
        ):
            if (
                self.outputs
                and isinstance(self.outputs[0], dict)
                and ("searches" in self.outputs[0] or "selected_region_ids" in self.outputs[0])
            ):
                payload = self.outputs.pop(0)
                if "selected_region_ids" in payload:
                    latest_question = _planner_latest_question(request)
                    payload = dict(payload)
                    payload["searches"] = [
                        {
                            "region_id": region_id,
                            "search_query": latest_question,
                        }
                        for region_id in payload.pop(
                            "selected_region_ids",
                            [],
                        )
                    ]
                content = json.dumps(payload, ensure_ascii=False)
                return ChatCompletionResponse(
                    content=content,
                    provider=self.provider,
                    model=self.model,
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )
            payload = {}
            for message in reversed(request.messages):
                try:
                    candidate = json.loads(message.content)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(candidate, dict) and "planning_state" in candidate:
                    payload = candidate
                    break
            content = json.dumps(
                {
                    "searches": [],
                },
                ensure_ascii=False,
            )
            return ChatCompletionResponse(
                content=content,
                provider=self.provider,
                model=self.model,
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        system_prompt = request.messages[0].content
        if "Answer Decision model" in system_prompt:
            payload = self.outputs.pop(0) if self.outputs else {}
            fixture = payload.get("test_answer") if isinstance(payload, dict) else None
            if isinstance(fixture, dict):
                self._pending_answer_fixture = fixture
                payload = fixture["decision"]
            content = json.dumps(payload, ensure_ascii=False)
            return ChatCompletionResponse(
                content=content,
                provider=self.provider,
                model=self.model,
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        if "Response Composer" in system_prompt and self._pending_answer_fixture is not None:
            payload = json.loads(
                json.dumps(
                    self._pending_answer_fixture["composition"],
                    ensure_ascii=False,
                )
            )
            state = json.loads(request.messages[-1].content)
            generated = state["composition_state"]["generated_image"]
            offered_visuals = {visual["visual_ref"] for visual in generated["visuals"]}
            payload["items"] = [
                item for item in payload["items"] if item.get("type") != "generated_visual" or item.get("visual") in offered_visuals
            ]
            self._pending_answer_fixture = None
            content = json.dumps(payload, ensure_ascii=False)
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


def _planner_latest_question(request: ChatCompletionRequest) -> str:
    for message in reversed(request.messages):
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        planning_state = payload.get("planning_state")
        if isinstance(planning_state, dict):
            return str(planning_state.get("latest_user_message") or "")
    return ""


def chat_answer_fixture(
    *,
    answer: str | None = None,
    spans: list[str] | None = None,
    visuals: list[str] | None = None,
    gap: str | None = None,
    gap_markdown: str | None = None,
    generated_image_prompt: str | None = None,
) -> dict[str, object]:
    selected_spans = spans or []
    selected_visuals = visuals or []
    if selected_spans:
        mode = "raw"
    elif answer is not None:
        mode = "general"
    else:
        mode = "gap"
    owners: list[str] = []
    for span in selected_spans:
        owner = _reference_owner(span)
        if owner not in owners:
            owners.append(owner)
    material_ids = {owner: f"material_{index}" for index, owner in enumerate(owners, start=1)}
    items: list[dict[str, object]] = []
    if answer is not None:
        items.append(
            {
                "type": "text",
                "markdown": answer,
                "materials": list(material_ids.values()),
            }
        )
    items.extend({"type": "source_visual", "visual": visual} for visual in selected_visuals)
    if generated_image_prompt is not None:
        items.append(
            {
                "type": "generated_visual",
                "visual": "generated_visual_1",
            }
        )
    return {
        "test_answer": {
            "decision": {
                "mode": mode,
                "spans": selected_spans,
                "visuals": selected_visuals,
                "gap": gap,
                "generated_image_prompt": generated_image_prompt,
            },
            "composition": {
                "items": items,
                "gap_markdown": (gap_markdown if gap_markdown is not None else gap),
            },
        },
    }


def _reference_owner(reference: str) -> str:
    parts = reference.split("_")
    return parts[1] if len(parts) > 2 else reference


class FakeWikiSearch:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return WikiSearchResponse(
            query=request.query,
            status="candidates",
            retrieval_mode="semantic_atom_claim_raw",
            results=[
                WikiSearchResult(
                    path="sources/Agent-Loop-Source.md",
                    title="Agent Loop Source",
                    score=12.0,
                    relevance="high",
                    reason="source record match",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                ),
                WikiSearchResult(
                    path="Agent-Loop.md",
                    title="Agent Loop",
                    score=9.0,
                    relevance="high",
                    reason="title match",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                    atom_traces=[
                        WikiAtomTrace(
                            atom_id="claim_agent_loop_cycle",
                            atom_type="claim",
                            text="Agent loop alternates reasoning, action, and observation.",
                            source_record_id="sr_agent_loop",
                        )
                    ],
                ),
                WikiSearchResult(
                    path="Session-Memory-Architecture-for-Agent-Loops.md",
                    title="Session Memory Architecture for Agent Loops",
                    score=7.0,
                    relevance="medium",
                    reason="related implementation page",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                ),
            ],
            raw_evidence=[],
            context_pack="Agent Loop context",
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
    available: bool = True

    def is_available(self, config_path=None):
        return self.available

    def generate(self, request: ImageGenerationRequest, *, config_path=None, provider_name=None):
        self.requests.append(request)
        return ImageGenerationResponse(
            provider=provider_name or "sensenova",
            model="sensenova-u1-fast",
            prompt=request.prompt,
            images=[GeneratedImage(b64_json="ZmFrZS1wbmc=", mime_type="image/png")],
            usage={"total_tokens": 1},
        )


class FakeChatKnowledge:
    query_status = "candidates"

    def retrieve_knowledge_batch(self, context, arguments):
        expressions = [
            item for item in arguments.get("query_expressions", []) if isinstance(item, dict) and str(item.get("query") or "").strip()
        ]
        query_results = []
        candidates_by_id = {}
        query_ids_by_evidence = {}
        terminal_statuses = []
        for index, expression in enumerate(expressions, start=1):
            query_id = str(expression.get("query_id") or f"q{index}")
            observation = self.search_knowledge(
                context,
                {"query": str(expression["query"]), "query_ids": [query_id]},
            )
            outcomes = observation.result.get("query_outcomes", [])
            status = self._terminal_status(outcomes)
            terminal_statuses.append(status)
            candidates = observation.result.get("candidates", [])
            query_results.append(
                {
                    "query_id": query_id,
                    "query": str(expression["query"]),
                    "status": status,
                    "candidate_count": len(candidates),
                    "outcomes": outcomes,
                }
            )
            for candidate in candidates:
                evidence_id = str(candidate["evidence_id"])
                candidates_by_id.setdefault(evidence_id, candidate)
                query_ids_by_evidence.setdefault(evidence_id, []).append(query_id)

        ordered_ids = list(candidates_by_id)
        read = (
            self.read_evidence(context, {"evidence_ids": ordered_ids})
            if ordered_ids
            else ChatToolTraceItem(tool="read_evidence", result={"raw_evidence": []})
        )
        raw_evidence = []
        for item in read.result.get("raw_evidence", []):
            payload = dict(item)
            payload["query_ids"] = query_ids_by_evidence.get(str(item["evidence_id"]), [])
            raw_evidence.append(payload)
        status = (
            "candidates"
            if raw_evidence
            else "no_match"
            if terminal_statuses and all(item == "no_match" for item in terminal_statuses)
            else terminal_statuses[0]
            if terminal_statuses
            else "integrity_error"
        )
        return ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            arguments=arguments,
            summary=f"Retrieved {len(raw_evidence)} active Raw source unit(s) for one answer.",
            citations=read.citations,
            result={
                "status": status,
                "query_expressions": expressions,
                "query_results": query_results,
                "raw_evidence": raw_evidence,
                "selected_evidence_ids": ordered_ids,
                "evidence_query_ids": query_ids_by_evidence,
                "candidate_count": len(ordered_ids),
                "selected_content_chars": sum(len(str(item.get("content") or item.get("excerpt") or "")) for item in raw_evidence),
                "raw_read_rounds": 1 if ordered_ids else 0,
                "raw_read_count": len(ordered_ids),
                "search_elapsed_ms": {str(item.get("query_id") or f"q{index}"): 0.0 for index, item in enumerate(expressions, start=1)},
                "raw_read_elapsed_ms": 0.0,
                "batch_elapsed_ms": 0.0,
                "warnings": [],
                "factual_authority": "active_raw_source_unit",
            },
        )

    @staticmethod
    def _terminal_status(outcomes):
        statuses = [str(item.get("status") or "") for item in outcomes]
        if "candidates" in statuses:
            return "candidates"
        if statuses and all(item == "no_match" for item in statuses):
            complete = all(
                item.get("exhausted") is True
                and all(channel.get("exhausted") is True for channel in item.get("channel_statuses", []) if isinstance(channel, dict))
                for item in outcomes
            )
            return "no_match" if complete else "resource_exhausted"
        return statuses[0] if statuses else "integrity_error"

    def search_knowledge(self, _context, arguments):
        candidates = (
            []
            if self.query_status != "candidates"
            else [
                {
                    "evidence_id": "ev:test",
                    "source_record_id": "sr_agent_loop",
                    "raw_revision_id": "rawrev:test",
                    "source_unit_id": "unit:test",
                    "score": 1.0,
                    "rank": 1,
                    "signals": [],
                }
            ]
        )
        channel_status = "completed" if self.query_status == "candidates" else "no_candidates"
        channel_statuses = [
            {"channel": "atom_claim", "status": channel_status, "match_count": len(candidates), "exhausted": True},
            {"channel": "raw_lexical", "status": channel_status, "match_count": len(candidates), "exhausted": True},
        ]
        return ChatToolTraceItem(
            tool="search_knowledge",
            arguments=arguments,
            summary="Found one claim candidate.",
            result={
                "query": arguments.get("query"),
                "candidates": candidates,
                "query_outcomes": [
                    {
                        "vault_id": "test",
                        "status": self.query_status,
                        "channel_statuses": channel_statuses,
                        "exhausted": self.query_status != "resource_exhausted",
                        "continuation_cursor": "cursor:test" if self.query_status == "resource_exhausted" else None,
                        "snapshot_generation": "generation:test",
                        "query_fingerprint": "sha256:test",
                    }
                ],
            },
        )

    def read_evidence(self, _context, arguments):
        evidence = {
            "evidence_id": "ev:test",
            "raw_record_id": "raw:test",
            "raw_revision_id": "rawrev:test",
            "source_unit_id": "unit:test",
            "source_record_id": "sr_agent_loop",
            "processing_record_id": "spr:test",
            "source_path": "raw/agent-loop.md",
            "unit_index": 0,
            "unit_type": "section",
            "title": "Agent Loop",
            "locator_page_paths": ["sources/Agent-Loop-Source.md"],
            "excerpt": "Agent Loop 是推理、行动和观察的循环。",
            "content": "Agent Loop 是推理、行动和观察的循环。",
            "excerpt_hash": "sha256:test",
            "char_start": 106,
            "char_end": 116,
            "source_unit_char_start": 100,
            "source_unit_char_end": 124,
        }
        return ChatToolTraceItem(
            tool="read_evidence",
            arguments=arguments,
            summary="Read one raw source unit.",
            citations=[
                ChatCitation(
                    kind="raw_evidence",
                    role="source",
                    path="raw/agent-loop.md",
                    title="Agent Loop",
                    evidence_id="ev:test",
                    raw_revision_id="rawrev:test",
                    source_unit_id="unit:test",
                    char_start=106,
                    char_end=116,
                )
            ],
            result={"raw_evidence": [evidence]},
        )


@dataclass
class FakeServices:
    chat_knowledge: FakeChatKnowledge = field(default_factory=FakeChatKnowledge)
    wiki_search: FakeWikiSearch = field(default_factory=FakeWikiSearch)
    wiki_pages: FakeWikiPages = field(default_factory=FakeWikiPages)
    vaults: FakeVaults = field(default_factory=FakeVaults)
    image_generation: FakeImageGeneration = field(default_factory=FakeImageGeneration)
    memory: MemoryService = field(default_factory=MemoryService)
    chat_sessions: ChatSessionStore = field(default_factory=ChatSessionStore)
