from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from pydantic import ValidationError

from knoarbor.audit.token_ledger import current_timestamp
from knoarbor.core.config import ModelRetryConfig, default_config_path, load_config
from knoarbor.core.errors import ExternalServiceError, ModelOutputError, StorageConflict, UserInputError
from knoarbor.core.schemas.chat import (
    ChatAnswerDraft,
    ChatAnswerMode,
    ChatAnswerProvenance,
    ChatEvent,
    ChatMessageItem,
    ChatRetrievalPlan,
    ChatRequest,
    ChatResponse,
    ChatRunLink,
    ChatSessionRecord,
    ChatToolPlan,
    ChatToolTraceItem,
)
from knoarbor.core.schemas.memory import MemoryCandidate, MemoryRecord
from knoarbor.services.chat_answer import (
    messages_chars,
    parse_json_object,
)
from knoarbor.services.chat_answer_decision import ChatAnswerDecisionService
from knoarbor.services.chat_answer_router import (
    ChatFinalizationState,
    finalize_chat_outcome,
)
from knoarbor.services.chat_context import (
    ChatContextEngine,
    latest_user_text,
    memory_target,
    session_dialogue_context,
    session_target,
)
from knoarbor.services.chat_dependencies import ChatAgentDependencies
from knoarbor.services.chat_execution_safety import ChatExecutionSafety, ChatExecutionSafetyExceeded
from knoarbor.services.chat_generated_images import delete_chat_request_artifacts
from knoarbor.services.chat_model_call import run_chat_model_call
from knoarbor.services.chat_persistence import ChatPersistenceCoordinator
from knoarbor.services.chat_reference_resolver import (
    ChatAnswerPresentation,
    answer_cleanup_citations,
    clean_answer_citation_paths,
    resolve_answer_presentation,
)
from knoarbor.services.chat_response_composer import (
    RESPONSE_COMPOSER_PROMPT,
    ChatGeneratedImageState,
    ChatGeneratedVisual,
    ChatResponseComposer,
)
from knoarbor.services.chat_tools import ChatToolExecutor
from knoarbor.core.vault_selection import resolve_vault_group
from knoarbor.runtime import runtime_logger
from knoarbor.runtime.local_operations import OperationCancellationToken
from knoarbor.retrieval.corpus_catalog import build_active_corpus_catalog
from knoarbor.semantic.contracts import load_prompt
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatMessage, ModelGateway

RETRIEVAL_PLANNER_PROMPT = load_prompt("wiki_chat_retrieval_planner.md")
LOGGER = runtime_logger(__name__)


@dataclass
class ChatAgentService:
    """Bounded product chat agent over existing wiki/runtime services."""

    client_factory: Callable[[ChatRequest], ChatClient] | None = None
    context_engine: ChatContextEngine = field(default_factory=ChatContextEngine)
    persistence: ChatPersistenceCoordinator = field(default_factory=ChatPersistenceCoordinator)

    def chat(
        self,
        request: ChatRequest,
        services: ChatAgentDependencies,
        *,
        event_callback: Callable[[ChatEvent], None] | None = None,
        cancellation: OperationCancellationToken | None = None,
        replacement_turn_id: str | None = None,
    ) -> ChatResponse:
        if cancellation is not None:
            cancellation.raise_if_stopped()
        started = time.perf_counter()
        client = self.client_factory(request) if self.client_factory else _client_from_request(request)
        chat_target = session_target(
            config_path=request.config_path,
            vault_path=request.vault_path,
            vault_id=request.vault_id,
            all_vaults=request.all_vaults,
        )
        resolved_request = request.model_copy(update={"vault_path": str(chat_target.path), "vault_id": chat_target.vault_id})
        existing_session = services.chat_sessions.load_existing(
            chat_target.path, resolved_request.session_id, sessions_dir=chat_target.sessions_dir
        )
        if resolved_request.session_id is not None and existing_session is None:
            raise UserInputError(f"Chat session does not exist: {resolved_request.session_id}")
        if existing_session is not None and resolved_request.expected_session_revision != existing_session.session_revision:
            raise StorageConflict(
                f"Chat session revision changed: expected {resolved_request.expected_session_revision}, "
                f"current {existing_session.session_revision}."
            )
        context_session = _retry_context_session(existing_session, replacement_turn_id)
        chat_id = resolved_request.session_id or (existing_session.session_id if existing_session else None)
        if chat_id is None:
            chat_id = services.chat_sessions.new_session_id()
        context = self.context_engine.build(
            resolved_request,
            services,
            chat_id=chat_id,
            existing_session=context_session,
            system_prompt=RESPONSE_COMPOSER_PROMPT,
        )
        effective_request = resolved_request.model_copy(update={"session_id": chat_id})
        runtime_config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
        safety = ChatExecutionSafety(
            max_wall_seconds=runtime_config.models.request_timeout_seconds,
        )
        loop = _ChatLoop(
            request=effective_request,
            current_messages=context.conversation_messages,
            services=services,
            client=client,
            chat_id=chat_id,
            initial_messages=context.model_messages,
            existing_session=context_session,
            model_retry=runtime_config.models.retry,
            memory_used=context.memory_used,
            warnings=context.warnings,
            event_callback=event_callback,
            cancellation=cancellation,
            safety=safety,
        )
        try:
            response = loop.run()
        except ChatExecutionSafetyExceeded as exc:
            response = loop.resource_exhausted(exc)
        except Exception:
            delete_chat_request_artifacts(chat_target.path, chat_id, resolved_request.request_id)
            raise
        if cancellation is not None:
            try:
                cancellation.raise_if_stopped()
            except Exception:
                delete_chat_request_artifacts(chat_target.path, chat_id, resolved_request.request_id)
                raise
        response.stats.update(
            {
                "chat_id": response.session_id,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "provider": getattr(client, "provider", response.stats.get("provider")),
                "model": getattr(client, "model", response.stats.get("model")),
                "retrieval_strategy": response.stats.get("retrieval_strategy", "canonical_evidence"),
                "session_vault_id": chat_target.vault_id,
                "session_vault_name": chat_target.vault_name,
            }
        )
        try:
            persisted = self.persistence.persist_response(
                services,
                chat_target=chat_target,
                request=resolved_request,
                response=response,
                request_messages=context.conversation_messages,
                call_records=loop.call_records,
                raise_if_cancelled=cancellation.raise_if_stopped if cancellation is not None else None,
                replacement_turn_id=replacement_turn_id,
            )
        except Exception:
            delete_chat_request_artifacts(chat_target.path, chat_id, resolved_request.request_id)
            raise
        if cancellation is not None:
            cancellation.raise_if_stopped()
        return persisted if request.include_trace else persisted.model_copy(update={"tool_trace": []})


@dataclass
class _ChatLoop:
    request: ChatRequest
    current_messages: list[ChatMessageItem]
    services: ChatAgentDependencies
    client: ChatClient
    chat_id: str
    initial_messages: list[ChatMessage]
    existing_session: ChatSessionRecord | None = None
    model_retry: ModelRetryConfig = field(default_factory=ModelRetryConfig)
    answer_decider: ChatAnswerDecisionService = field(default_factory=ChatAnswerDecisionService)
    response_composer: ChatResponseComposer = field(default_factory=ChatResponseComposer)
    trace: list[ChatToolTraceItem] = field(default_factory=list)
    events: list[ChatEvent] = field(default_factory=list)
    run_links: list[ChatRunLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_calls: int = 0
    total_usage: dict[str, int] = field(default_factory=dict)
    call_records: list[dict[str, object]] = field(default_factory=list)
    memory_used: list[MemoryRecord] = field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = field(default_factory=list)
    memory_writes: list[MemoryRecord] = field(default_factory=list)
    event_callback: Callable[[ChatEvent], None] | None = None
    cancellation: OperationCancellationToken | None = None
    safety: ChatExecutionSafety | None = None
    terminal_query_outcome: str = "not_applicable"
    last_final_draft: ChatAnswerDraft | None = None
    last_final_mode: ChatAnswerMode | None = None

    def run(self) -> ChatResponse:
        self._raise_if_stopped()
        self._event("chat_started", message="Chat request started.")
        query = latest_user_text(self.current_messages)
        executor = ChatToolExecutor(
            request=self.request,
            services=self.services,
            event_callback=self._tool_event,
            raise_if_stopped=self._raise_if_stopped,
            before_tool_call=self.safety.before_tool_call if self.safety is not None else None,
            observe_tool_result=self.safety.observe_tool_result if self.safety is not None else None,
        )
        answer_turn = 1
        direct_capability = _direct_capability(query)
        if direct_capability is not None:
            direct_observations: list[ChatToolTraceItem] = []
            if direct_capability == "list_vaults":
                direct_plan = ChatToolPlan(
                    tool_calls=[{"name": direct_capability, "arguments": {}}],
                    reason="Execute an explicitly requested product capability.",
                    confidence=1.0,
                )
                direct_observations = executor.execute(direct_plan, query)
                self.trace.extend(direct_observations)
                for observation in direct_observations:
                    _merge_usage(self.total_usage, _tool_usage(observation))
                if any(item.status == "error" for item in direct_observations):
                    raise RuntimeError(f"Direct Chat capability failed: {direct_capability}.")
            provenance = ChatAnswerProvenance(
                mode="direct_capability",
                query_outcome="not_applicable",
                chat_outcome="direct",
            )
            response = self._answer_response(
                ChatAnswerDraft(answer=_direct_capability_answer(query, direct_capability, direct_observations)),
                turns=answer_turn,
                provenance=provenance,
                allow_citations=False,
            )
            response.stats["retrieval_strategy"] = "direct_capability"
            return response

        if self.safety is not None:
            self.safety.ensure_tool_capacity()
        retrieval_plans: list[ChatRetrievalPlan] = []
        query_directions: list[tuple[str, str | None, str]] = []
        retrieval_attempts = 0

        def execute_batch(
            directions: list[tuple[str, str | None, str]],
        ) -> tuple[list[ChatToolTraceItem], dict[str, Any], str]:
            nonlocal retrieval_attempts
            retrieval_attempts += 1
            query_expressions = [
                {
                    "query_id": f"q{index}",
                    "query": expression,
                    **({"region_id": region_id} if region_id is not None else {}),
                    "group_id": group_id,
                }
                for index, (expression, region_id, group_id) in enumerate(
                    directions,
                    start=1,
                )
            ]
            batch_plan = ChatToolPlan(
                tool_calls=[
                    {
                        "name": "retrieve_knowledge_batch",
                        "arguments": {
                            "query_expressions": query_expressions,
                        },
                    }
                ],
                reason="Execute one Query-owned batch retrieval and Active Raw evidence assembly.",
                confidence=1.0,
            )
            batch_items = executor.execute(batch_plan, query)
            if not batch_items or any(item.status == "error" for item in batch_items):
                return batch_items, {}, "integrity_error"
            result = batch_items[0].result
            return batch_items, result, str(result.get("status") or "integrity_error")

        try:
            retrieval_plan, corpus_catalog = self._plan_retrieval(
                query,
                turn=1,
            )
        except (ExternalServiceError, ModelOutputError, RuntimeError):
            self.warnings.append("retrieval_planner_unavailable")
        else:
            retrieval_plans.append(retrieval_plan)
            query_directions.extend(
                _retrieval_search_directions(
                    query=query,
                    plan=retrieval_plan,
                )
            )
        if not query_directions:
            query_directions.append((query, None, "region_unscoped"))

        batch_observations, batch_result, query_outcome = execute_batch(query_directions)
        self.trace.extend(batch_observations)
        self.terminal_query_outcome = query_outcome

        evidence_ids = [
            str(item.get("evidence_id"))
            for item in batch_result.get("raw_evidence", [])
            if isinstance(item, dict) and item.get("evidence_id")
        ]

        if query_outcome in {"candidates", "no_match"}:
            answer_turn = 2
            answer_result = self._compose_answer(
                batch_observations,
                evidence_ids,
                query_outcome,
                answer_turn,
                executor=executor,
                query=query,
                image_generation_available=executor.has_tool("generate_image"),
            )
            if answer_result.has_supported_answer:
                answer_mode = "knowledge_grounded_with_gap" if answer_result.has_gap else "knowledge_grounded"
                chat_outcome = finalize_chat_outcome(
                    ChatFinalizationState(
                        query_outcomes=("candidates",),
                        has_supported_answer=True,
                        has_gap=answer_result.has_gap,
                    )
                )
                source_path = "local_knowledge"
            elif answer_result.has_general_answer:
                answer_mode = "general_knowledge"
                chat_outcome = "no_match" if query_outcome == "no_match" else "planning_exhausted"
                source_path = "model_general"
            else:
                answer_mode = "knowledge_gap"
                chat_outcome = "no_match" if query_outcome == "no_match" else "planning_exhausted"
                source_path = "knowledge_gap"
            self._select_answer_source(source_path, answer_turn)
            final_draft = answer_result.draft
            if self.event_callback:
                self._answer_delta_callback(answer_turn)(final_draft.answer)
            provenance = ChatAnswerProvenance(
                mode=answer_mode,
                query_outcome=query_outcome,
                chat_outcome=chat_outcome,
            )
            response = self._answer_response(
                final_draft,
                turns=answer_turn,
                provenance=provenance,
                allow_citations=answer_result.has_supported_answer,
            )
        elif query_outcome == "resource_exhausted":
            chat_outcome = finalize_chat_outcome(
                ChatFinalizationState(
                    query_outcomes=("resource_exhausted",),
                    all_searches_exhausted=False,
                    stop_reason="resource_exhausted",
                )
            )
            provenance = ChatAnswerProvenance(
                mode="knowledge_gap",
                query_outcome="resource_exhausted",
                chat_outcome=chat_outcome,
            )
            response = self._answer_response(
                ChatAnswerDraft(answer="本次知识检索触及资源安全边界；这不代表知识库中没有相关内容。请缩小问题范围后重试。"),
                turns=answer_turn,
                provenance=provenance,
                allow_citations=False,
            )
        else:
            chat_outcome = (
                "integrity_error" if query_outcome == "integrity_error" else ("cancelled" if query_outcome == "cancelled" else "tool_error")
            )
            provenance = ChatAnswerProvenance(
                mode="knowledge_gap",
                query_outcome=query_outcome,  # type: ignore[arg-type]
                chat_outcome=chat_outcome,
            )
            response = self._answer_response(
                ChatAnswerDraft(answer=_retrieval_failure_answer(query_outcome)),
                turns=answer_turn,
                provenance=provenance,
                allow_citations=False,
            )

        response.stats["retrieval_strategy"] = "query_owned_batch_raw"
        response.stats["query_outcome"] = query_outcome
        response.stats["chat_outcome"] = response.answer_provenance.chat_outcome
        response.stats["answer_mode"] = response.answer_provenance.mode
        response.stats["retrieval_planning"] = [plan.model_dump(mode="json") for plan in retrieval_plans]
        response.stats["retrieval_attempts"] = retrieval_attempts
        response.stats["retrieval_batch"] = {
            key: batch_result.get(key)
            for key in (
                "status",
                "query_expressions",
                "query_results",
                "group_results",
                "selected_evidence_ids",
                "evidence_query_ids",
                "candidate_count",
                "global_eligible_candidate_count",
                "global_result_window",
                "selected_content_chars",
                "evidence_packet_chars",
                "evidence_packet_reduction_ratio",
                "raw_read_rounds",
                "raw_read_count",
                "search_elapsed_ms",
                "raw_read_elapsed_ms",
                "batch_elapsed_ms",
                "warnings",
            )
            if key in batch_result
        }
        return response

    def _raise_if_stopped(self) -> None:
        if self.cancellation is not None:
            self.cancellation.raise_if_stopped()
        if self.safety is not None:
            self.safety.check()

    def resource_exhausted(self, exc: ChatExecutionSafetyExceeded) -> ChatResponse:
        grounded = self.last_final_mode in {
            "knowledge_grounded",
            "knowledge_grounded_with_gap",
        }
        completed = self.last_final_draft is not None
        chat_outcome = finalize_chat_outcome(
            ChatFinalizationState(
                query_outcomes=(),
                stop_reason="resource_exhausted",
            )
        )
        provenance = ChatAnswerProvenance(
            mode=(self.last_final_mode if completed and self.last_final_mode is not None else "knowledge_gap"),
            query_outcome=("candidates" if completed or self.terminal_query_outcome == "candidates" else "resource_exhausted"),
            chat_outcome=chat_outcome,
        )
        draft = self.last_final_draft or ChatAnswerDraft(answer="本轮检索达到资源安全边界，未进入通用知识回答。可以缩小问题范围后继续。")
        self.warnings.append(f"chat_execution_safety:{exc.reason}")
        response = self._answer_response(
            draft,
            turns=max(1, self.model_calls + 1),
            provenance=provenance,
            allow_citations=grounded,
        )
        response.stats["execution_safety"] = exc.usage
        response.stats["query_outcome"] = provenance.query_outcome
        response.stats["chat_outcome"] = provenance.chat_outcome
        response.stats["answer_mode"] = provenance.mode
        return response

    def _select_answer_source(self, source_path: str, turn: int) -> None:
        self._event(
            "answer_source_selected",
            message="Chat answer source path selected.",
            turn=turn,
            payload={
                "source_path": source_path,
                "provisional": False,
            },
        )

    def _plan_retrieval(
        self,
        query: str,
        *,
        turn: int,
    ) -> tuple[ChatRetrievalPlan, dict[str, object]]:
        corpus_catalog = build_active_corpus_catalog(
            resolve_vault_group(
                vault_path=self.request.vault_path,
                vault_id=self.request.vault_id,
                vault_ids=self.request.vault_ids,
                all_vaults=self.request.all_vaults,
                config_path=self.request.config_path,
            )
        )
        messages = _retrieval_planning_messages(
            self.existing_session,
            query=query,
            corpus_catalog=corpus_catalog,
        )
        prompt_chars = messages_chars(messages)
        self._event(
            "model_call_started",
            message="Calling retrieval planner.",
            turn=turn,
            payload={"phase": "retrieval_planner"},
        )
        validated: dict[str, ChatRetrievalPlan] = {}

        def validate_completion(completion) -> None:
            parsed = _parse_retrieval_plan(completion.content)
            catalog_entries = _corpus_catalog_entries(corpus_catalog)
            allowed_ids = set(catalog_entries)
            unknown = [search.region_id for search in parsed.searches if search.region_id not in allowed_ids]
            if unknown:
                raise ModelOutputError("Retrieval planner returned unknown region IDs: " + ", ".join(unknown))
            validated["plan"] = parsed

        call = run_chat_model_call(
            client=self.client,
            request=ChatCompletionRequest(
                messages=messages,
                temperature=0,
                max_tokens=_max_tokens(self.request),
            ),
            retry=self.model_retry,
            phase="retrieval_planner",
            turn=turn,
            prompt_chars=prompt_chars,
            raise_if_cancelled=self._raise_if_stopped,
            before_model_call=self.safety.before_model_call if self.safety is not None else None,
            completion_validator=validate_completion,
        )
        completion = call.completion
        self.model_calls += 1
        _merge_usage(self.total_usage, completion.usage)
        self._event(
            "model_call_finished",
            message="Retrieval planner finished.",
            turn=turn,
            payload={"usage": completion.usage, "elapsed_seconds": completion.elapsed_seconds},
        )
        self.call_records.append(call.call_record)
        return validated["plan"], corpus_catalog

    def _compose_answer(
        self,
        observations: list[ChatToolTraceItem],
        evidence_ids: list[str],
        retrieval_outcome: str,
        turn: int,
        *,
        executor: ChatToolExecutor,
        query: str,
        image_generation_available: bool,
    ):
        self._event(
            "model_call_started",
            message="Calling Chat Answer Decision model.",
            turn=turn,
            payload={"phase": "answer", "semantic_phase": "answer_decision"},
        )
        decision_result = self.answer_decider.decide(
            client=self.client,
            current_messages=self.current_messages,
            model_context_messages=_answer_context_messages(self.initial_messages),
            existing_session=self.existing_session,
            observations=observations,
            evidence_ids=evidence_ids,
            retrieval_outcome=retrieval_outcome,
            image_generation_available=image_generation_available,
            turn=turn,
            max_tokens=_max_tokens(self.request),
            retry=self.model_retry,
            raise_if_cancelled=self._raise_if_stopped,
            before_model_call=self.safety.before_model_call if self.safety is not None else None,
        )
        self._record_model_stage(
            completion=decision_result.completion,
            call_record=decision_result.call_record,
            turn=turn,
            phase="answer_decision",
        )
        generated_image = self._generate_requested_image(
            decision_result.decision.generated_image_prompt,
            executor,
            query=query,
        )
        self._event(
            "model_call_started",
            message="Calling Chat Response Composer.",
            turn=turn,
            payload={"phase": "answer", "semantic_phase": "response_composer"},
        )
        result = self.response_composer.compose(
            client=self.client,
            current_messages=self.current_messages,
            model_context_messages=_answer_context_messages(self.initial_messages),
            existing_session=self.existing_session,
            decision_result=decision_result,
            generated_image=generated_image,
            turn=turn,
            max_tokens=_max_tokens(self.request),
            retry=self.model_retry,
            raise_if_cancelled=self._raise_if_stopped,
            before_model_call=self.safety.before_model_call if self.safety is not None else None,
        )
        self._record_model_stage(
            completion=result.completion,
            call_record=result.call_record,
            turn=turn,
            phase="response_composer",
        )
        self.last_final_draft = result.draft
        self.last_final_mode = (
            "knowledge_grounded_with_gap"
            if result.has_supported_answer and result.has_gap
            else "knowledge_grounded"
            if result.has_supported_answer
            else "general_knowledge"
            if result.has_general_answer
            else "knowledge_gap"
        )
        return result

    def _generate_requested_image(
        self,
        prompt: str | None,
        executor: ChatToolExecutor,
        *,
        query: str,
    ) -> ChatGeneratedImageState:
        if prompt is None:
            return ChatGeneratedImageState(status="not_requested")
        plan = ChatToolPlan(
            tool_calls=[
                {
                    "name": "generate_image",
                    "arguments": {"prompt": prompt},
                }
            ],
            reason="Generate one decision-authorized visual before final response composition.",
            confidence=1.0,
        )
        generated = executor.execute(plan, query)
        self.trace.extend(generated)
        successful = [item for item in generated if item.status == "ok"]
        for observation in successful:
            _merge_usage(self.total_usage, _tool_usage(observation))
        if not successful:
            delete_chat_request_artifacts(
                self.request.vault_path,
                self.chat_id,
                self.request.request_id,
            )
            self.warnings.append("optional_image_generation_failed")
            return ChatGeneratedImageState(status="failed")
        visuals = _generated_visuals(
            successful,
            prompt=prompt,
            query=query,
        )
        if not visuals:
            delete_chat_request_artifacts(
                self.request.vault_path,
                self.chat_id,
                self.request.request_id,
            )
            self.warnings.append("optional_image_generation_empty")
            return ChatGeneratedImageState(status="failed")
        return ChatGeneratedImageState(
            status="available",
            visuals=visuals,
        )

    def _record_model_stage(
        self,
        *,
        completion,
        call_record: dict[str, object],
        turn: int,
        phase: str,
    ) -> None:
        self.model_calls += 1
        _merge_usage(self.total_usage, completion.usage)
        self._event(
            "model_call_finished",
            message="Chat semantic model call finished.",
            turn=turn,
            payload={
                "phase": "answer",
                "semantic_phase": phase,
                "usage": completion.usage,
                "elapsed_seconds": completion.elapsed_seconds,
            },
        )
        self.call_records.append(call_record)

    def _answer_response(
        self,
        draft: ChatAnswerDraft,
        turns: int,
        *,
        provenance: ChatAnswerProvenance,
        allow_citations: bool = True,
    ) -> ChatResponse:
        presentation = (
            resolve_answer_presentation(draft.citations, self.trace, answer=draft.answer)
            if allow_citations
            else ChatAnswerPresentation(answer=draft.answer, citations=[])
        )
        answer = clean_answer_citation_paths(
            presentation.answer,
            answer_cleanup_citations(self.trace, presentation.citations),
            latest_user_text=latest_user_text(self.current_messages),
        )
        self._capture_memory()
        self._event(
            "final_answer_ready", message="Final chat answer is ready.", turn=turns, payload={"citation_count": len(presentation.citations)}
        )
        return ChatResponse(
            request_id=self.request.request_id,
            execution_id=self.request.execution_id,
            session_id=self.request.session_id,
            session_revision=(self.existing_session.session_revision if self.existing_session else 0) + 1,
            turn_id=f"turn_{uuid4().hex}",
            answer=answer,
            answer_provenance=provenance,
            citations=presentation.citations,
            hidden_evidence_count=presentation.hidden_evidence_count,
            citation_warnings=presentation.warnings,
            tool_trace=self.trace,
            events=self.events,
            run_links=self.run_links,
            memory_used=self.memory_used,
            memory_candidates=self.memory_candidates,
            memory_writes=self.memory_writes,
            stats=self._stats(turns),
            warnings=[*self.warnings, *presentation.warnings],
        )

    def _answer_delta_callback(self, turn: int) -> Callable[[str], None]:
        def callback(delta: str) -> None:
            self._event(
                "answer_delta",
                message="Chat answer token received.",
                turn=turn,
                payload={"delta": delta},
            )

        return callback

    def _stats(self, turns: int) -> dict[str, Any]:
        return {
            "turns": turns,
            "model_calls": self.model_calls,
            "tool_calls": len(self.trace),
            "memory_used": len(self.memory_used),
            "memory_candidates": len(self.memory_candidates),
            "memory_writes": len(self.memory_writes),
            "usage": dict(self.total_usage),
            "model_phases": _model_phase_stats(self.call_records),
            "total_tokens": self.total_usage.get("total_tokens", 0),
            "execution_safety": self.safety.payload() if self.safety is not None else {},
        }

    def _capture_memory(self) -> None:
        target = memory_target(self.request)
        if target is None:
            return
        config = load_config(Path(self.request.config_path).expanduser().resolve() if self.request.config_path else default_config_path())
        candidates, writes = self.services.memory.capture_explicit_memory(
            vault_path=target.path,
            vault_id=target.vault_id,
            messages=self.current_messages,
            config=config.memory,
            chat_id=self.chat_id,
        )
        self.memory_candidates = candidates
        self.memory_writes = writes

    def _event(
        self,
        event_type: str,
        *,
        message: str = "",
        tool: str | None = None,
        turn: int | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = ChatEvent(
            event_type=event_type,  # type: ignore[arg-type]
            created_at=current_timestamp(),
            message=message,
            tool=tool,
            turn=turn,
            status=status,  # type: ignore[arg-type]
            payload=payload or {},
        )
        self.events.append(event)
        if self.event_callback:
            self.event_callback(event)
        LOGGER.info(
            "chat_event chat_id=%s event=%s turn=%s tool=%s status=%s usage=%s elapsed_seconds=%s",
            self.chat_id,
            event_type,
            turn,
            tool or "-",
            status or "-",
            _event_usage(payload),
            _event_elapsed(payload),
        )

    def _tool_event(self, event_type: str, message: str, tool: str | None, turn: int | None, status: str | None) -> None:
        self._event(event_type, message=message, tool=tool, turn=turn, status=status)


def _client_from_request(request: ChatRequest) -> ChatClient:
    config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
    provider = request.provider or config.models.default_provider
    if not provider:
        raise UserInputError("No model provider configured for chat.")
    provider_config = config.models.providers.get(provider)
    if provider_config is None:
        raise UserInputError(f"Unknown model provider: {provider}")
    return ModelGateway.from_config(provider, provider_config, timeout_seconds=config.models.request_timeout_seconds)


def _retry_context_session(
    existing_session: ChatSessionRecord | None,
    replacement_turn_id: str | None,
) -> ChatSessionRecord | None:
    if existing_session is None or replacement_turn_id is None:
        return existing_session
    if not existing_session.turns or existing_session.turns[-1].turn_id != replacement_turn_id:
        raise StorageConflict("Chat retry target changed before execution.")
    target = existing_session.turns[-1]
    removed_message_ids = {target.user_message.message_id, target.assistant_message.message_id}
    return existing_session.model_copy(
        update={
            "messages": [message for message in existing_session.messages if message.message_id not in removed_message_ids],
            "turns": existing_session.turns[:-1],
        }
    )


def _max_tokens(request: ChatRequest) -> int | None:
    if request.max_tokens is not None:
        return request.max_tokens
    config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
    return config.models.resolve_max_tokens(request.provider)


def _event_usage(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "-"
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return "-"
    total = usage.get("total_tokens")
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if total is None and prompt is None and completion is None:
        return "-"
    return f"total={total or 0},prompt={prompt or 0},completion={completion or 0}"


def _event_elapsed(payload: dict[str, Any] | None) -> str:
    if not payload or payload.get("elapsed_seconds") is None:
        return "-"
    return str(payload.get("elapsed_seconds"))


def _answer_context_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Preserve recalled user memory without forwarding workspace identities."""

    return [
        message.model_copy(update={"role": "user"})
        for message in messages
        if message.role == "system" and message.content.startswith("<knoarbor-memory-context>")
    ]


def _model_phase_stats(call_records: list[dict[str, object]]) -> list[dict[str, object]]:
    phases: dict[str, dict[str, object]] = {}
    for call in call_records:
        phase = str(call.get("phase") or "unknown")
        item = phases.setdefault(
            phase,
            {
                "phase": phase,
                "calls": 0,
                "prompt_tokens": 0,
                "prompt_cached_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "prompt_chars": 0,
                "elapsed_seconds": 0.0,
            },
        )
        item["calls"] = int(item["calls"]) + 1
        for key in ("prompt_tokens", "prompt_cached_tokens", "completion_tokens", "total_tokens", "prompt_chars"):
            item[key] = int(item[key]) + int(call.get(key) or 0)
        item["elapsed_seconds"] = float(item["elapsed_seconds"]) + float(call.get("elapsed_seconds") or 0)
    for item in phases.values():
        prompt_tokens = int(item["prompt_tokens"])
        item["prompt_cache_rate"] = int(item["prompt_cached_tokens"]) / prompt_tokens if prompt_tokens else None
        item["elapsed_seconds"] = round(float(item["elapsed_seconds"]), 3)
    return list(phases.values())


def _parse_retrieval_plan(content: str) -> ChatRetrievalPlan:
    payload = parse_json_object(content)
    try:
        return ChatRetrievalPlan.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise ModelOutputError(f"Retrieval planner returned invalid JSON: {exc}") from exc


def _retrieval_planning_messages(
    existing_session: ChatSessionRecord | None,
    *,
    query: str,
    corpus_catalog: dict[str, object],
) -> list[ChatMessage]:
    planning_state = {
        "active_corpus_outline": corpus_catalog,
        "conversation_context": session_dialogue_context(existing_session),
        "latest_user_message": query,
    }
    return [
        ChatMessage(role="system", content=RETRIEVAL_PLANNER_PROMPT),
        ChatMessage(
            role="user",
            content=json.dumps(
                {"planning_state": planning_state},
                ensure_ascii=False,
            ),
        ),
    ]


@dataclass(frozen=True)
class _CorpusCatalogEntry:
    region_id: str
    language_hint: str


def _corpus_catalog_entries(
    corpus_catalog: dict[str, object],
) -> dict[str, _CorpusCatalogEntry]:
    output: dict[str, _CorpusCatalogEntry] = {}
    vaults = corpus_catalog.get("vaults", [])
    if not isinstance(vaults, list):
        return output
    for vault in vaults:
        if not isinstance(vault, dict):
            continue
        documents = vault.get("documents", [])
        if not isinstance(documents, list):
            continue
        for document in documents:
            if not isinstance(document, dict):
                continue
            regions = [
                (
                    str(document.get("region_id") or "").strip(),
                    str(document.get("language_hint") or "unknown").strip(),
                )
            ]
            sections = document.get("sections", [])
            if isinstance(sections, list):
                regions.extend(
                    (
                        str(section.get("region_id") or "").strip(),
                        str(section.get("language_hint") or document.get("language_hint") or "unknown").strip(),
                    )
                    for section in sections
                    if isinstance(section, dict)
                )
            for region_id, language_hint in regions:
                if region_id:
                    output[region_id] = _CorpusCatalogEntry(
                        region_id=region_id,
                        language_hint=language_hint,
                    )
    return output


def _retrieval_search_directions(
    *,
    query: str,
    plan: ChatRetrievalPlan,
) -> list[tuple[str, str, str]]:
    """Compile literal and model-authored variants into one group per region."""

    directions: list[tuple[str, str, str]] = []
    for search in plan.searches:
        group_id = f"region:{search.region_id}"
        directions.append((query, search.region_id, group_id))
        if _normalized_query(search.search_query) != _normalized_query(query):
            directions.append((search.search_query, search.region_id, group_id))
    return directions


def _normalized_query(value: str) -> str:
    return " ".join(value.casefold().split())


def _text_language(value: str) -> str:
    cjk = sum(1 for char in value if "\u3400" <= char <= "\u9fff")
    latin = sum(1 for char in value if char.isascii() and char.isalpha())
    if cjk >= 2 and cjk >= latin * 0.25:
        return "zh"
    if latin:
        return "en"
    return "source"


def _direct_capability(query: str) -> str | None:
    text = query.strip().lower()
    if not text:
        return "help"
    if text in {
        "hi",
        "hello",
        "hey",
        "你好",
        "您好",
    }:
        return "greeting"
    if text in {
        "你是谁",
        "你能做什么",
        "你可以做什么",
        "help",
        "帮助",
        "怎么用",
        "如何使用",
    }:
        return "help"
    if any(term in text for term in ("有哪些知识库", "知识库列表", "列出知识库", "list vaults", "list knowledge bases")):
        return "list_vaults"
    return None


def _knowledge_gap_answer(
    chat_outcome: str,
    *,
    calibration_pending: bool = False,
    local_evidence_required: bool = False,
) -> str:
    if chat_outcome == "needs_clarification":
        return "这个问题包含尚未解析的指代，请明确你指的是哪个对象或前文内容。"
    if chat_outcome == "planning_exhausted":
        return "本轮检索没有形成可验证的回答依据，也不足以确认知识库确实无相关内容。请换一种更具体的问法。"
    if calibration_pending:
        return "当前知识库中没有找到相关材料；通用知识扩展尚未通过检索无匹配质量校准，因此本轮没有调用模型的通用知识。"
    if local_evidence_required:
        return "当前知识库中没有找到可支持该说法的内容，因此无法确认，也不能把模型的通用知识当作文档结论。"
    return "当前知识库中没有找到与这个问题相关的材料。"


def _retrieval_failure_answer(query_outcome: str) -> str:
    if query_outcome == "index_unavailable":
        return "当前知识检索快照不可用，无法安全判断知识库中是否存在相关内容；本轮未转入通用知识回答。"
    if query_outcome == "integrity_error":
        return "知识检索结果未通过完整性校验，本轮未生成知识回答，也未转入通用知识回答。"
    if query_outcome == "cancelled":
        return "本轮知识检索已取消。"
    return "本轮知识检索请求无效或作用域不可用，未生成知识回答。"


def _direct_capability_answer(_query: str, capability: str, observations: list[ChatToolTraceItem]) -> str:
    if capability == "greeting":
        return "你好，我是 KnoArbor。你可以询问知识库内容，也可以在允许模型扩展时询问知识库之外的一般问题。"
    if capability == "list_vaults":
        vaults = observations[0].result.get("vaults", []) if observations else []
        labels = [
            str(item.get("name") or item.get("vault_id"))
            for item in vaults
            if isinstance(item, dict) and (item.get("name") or item.get("vault_id"))
        ]
        return f"当前配置了 {len(labels)} 个知识库：{'、'.join(labels)}。" if labels else "当前没有配置可用的知识库。"
    return "我可以帮助你检索 KnoArbor 中的知识、查看引用来源，并说明当前界面与设置的使用方式。"


def _generated_visuals(
    observations: list[ChatToolTraceItem],
    *,
    prompt: str,
    query: str,
) -> tuple[ChatGeneratedVisual, ...]:
    provenance_label = (
        "**本轮生成图片（非知识库证据）**" if _text_language(query) == "zh" else "**Generated this turn (not knowledge-base evidence)**"
    )
    visuals: list[ChatGeneratedVisual] = []
    for observation in observations:
        if observation.tool != "generate_image":
            continue
        for image in observation.result.get("images", []):
            if not isinstance(image, dict) or not image.get("markdown"):
                continue
            visuals.append(
                ChatGeneratedVisual(
                    visual_ref=f"generated_visual_{len(visuals) + 1}",
                    description=prompt,
                    markdown=(provenance_label + "\n\n" + str(image["markdown"])),
                )
            )
    return tuple(visuals)


def _merge_usage(target: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        target[key] = target.get(key, 0) + int(value)


def _tool_usage(observation: ChatToolTraceItem) -> dict[str, int]:
    usage = observation.result.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {str(key): int(value) for key, value in usage.items() if isinstance(value, int) and not isinstance(value, bool)}
