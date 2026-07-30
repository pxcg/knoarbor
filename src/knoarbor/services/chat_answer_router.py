from __future__ import annotations

from dataclasses import dataclass

from knoarbor.core.schemas.chat import ChatQueryOutcome, ChatSemanticOutcome


@dataclass(frozen=True)
class ChatFinalizationState:
    query_outcomes: tuple[ChatQueryOutcome, ...]
    has_supported_answer: bool = False
    has_gap: bool = False
    all_searches_exhausted: bool = False
    unresolved_reference: bool = False
    tool_failed: bool = False
    stop_reason: str = ""


def finalize_chat_outcome(state: ChatFinalizationState) -> ChatSemanticOutcome:
    """Pure terminal reducer; only this function assigns semantic Chat outcome."""

    outcomes = set(state.query_outcomes)
    if state.stop_reason == "cancelled" or "cancelled" in outcomes:
        return "cancelled"
    if state.stop_reason == "resource_exhausted" or "resource_exhausted" in outcomes:
        return "resource_exhausted"
    if state.tool_failed:
        return "tool_error"
    if outcomes.intersection({"integrity_error", "index_unavailable", "invalid_scope", "invalid_query"}):
        return "integrity_error"

    if "candidates" in outcomes:
        if state.has_supported_answer:
            return "partial" if state.has_gap else "sufficient"
        return "needs_clarification" if state.unresolved_reference else "planning_exhausted"

    if (
        outcomes
        and outcomes == {"no_match"}
        and state.all_searches_exhausted
        and not state.unresolved_reference
    ):
        return "no_match"
    if state.unresolved_reference:
        return "needs_clarification"
    return "planning_exhausted"
