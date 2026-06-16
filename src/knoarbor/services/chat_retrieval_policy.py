from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knoarbor.core.schemas.chat import ChatSessionRecord, ChatToolPlan, ChatToolTraceItem


@dataclass(frozen=True)
class ChatPlanAdjustment:
    """A code-owned correction applied after model tool planning."""

    kind: str
    reason: str
    original_plan: dict[str, Any]
    adjusted_plan: dict[str, Any]


@dataclass(frozen=True)
class ChatRetrievalPolicy:
    """Keeps chat retrieval aligned with wiki-first multi-turn semantics.

    The model planner proposes tools, but this policy owns stable product
    behavior: direct follow-up synthesis should reuse the session's maintained
    evidence instead of launching a broad, literal search that can drift.
    """

    def adjust_plan(
        self,
        plan: ChatToolPlan,
        *,
        query: str,
        existing_session: ChatSessionRecord | None,
        observations: list[ChatToolTraceItem],
    ) -> tuple[ChatToolPlan, ChatPlanAdjustment | None]:
        if observations or existing_session is None:
            return plan, None
        if not _is_context_synthesis_request(query):
            return plan, None
        if not _has_reusable_wiki_evidence(existing_session):
            return plan, None
        if _plan_only_finishes_or_reuses(plan):
            return plan, None
        adjusted = ChatToolPlan(
            tool_calls=[
                {"name": "reuse_context", "arguments": {"scope": "recent_session_evidence"}},
                {"name": "finish_answer", "arguments": {"reason": "The latest request asks to synthesize prior discussion."}},
            ],
            reason="Context-synthesis follow-up should reuse prior session evidence instead of starting a broad new search.",
            confidence=max(plan.confidence, 0.9),
        )
        return adjusted, ChatPlanAdjustment(
            kind="context_synthesis_reuse",
            reason=adjusted.reason,
            original_plan=plan.model_dump(mode="json"),
            adjusted_plan=adjusted.model_dump(mode="json"),
        )


def _plan_only_finishes_or_reuses(plan: ChatToolPlan) -> bool:
    return bool(plan.tool_calls) and all(call.name in {"reuse_context", "finish_answer"} for call in plan.tool_calls)


def _has_reusable_wiki_evidence(session: ChatSessionRecord) -> bool:
    traces = [item for turn in session.turns[-6:] for item in turn.tool_trace] or session.tool_trace[-6:]
    for item in traces:
        if item.status != "ok":
            continue
        if item.tool == "read_wiki_page":
            return True
        if item.tool in {"query_wiki", "reuse_context"} and isinstance(item.result.get("evidence_pack"), dict):
            pack = item.result["evidence_pack"]
            if pack.get("primary_pages") or pack.get("primary_page") or item.citations:
                return True
    return False


def _is_context_synthesis_request(query: str) -> bool:
    text = query.strip().lower()
    if not text:
        return False
    synthesis_terms = (
        "总结",
        "汇总",
        "整理",
        "归纳",
        "梳理",
        "形成",
        "生成",
        "输出",
        "大纲",
        "方案",
        "路线图",
        "技术设计",
        "设计文档",
        "文档大纲",
        "最后",
        "整体",
        "整个",
        "这些模块",
        "这些内容",
        "前面",
        "上面",
        "刚才",
        "this plan",
        "the plan",
        "summarize",
        "synthesi",
        "outline",
        "roadmap",
        "technical design",
        "design doc",
        "based on the above",
        "previous discussion",
    )
    has_synthesis = any(term in text for term in synthesis_terms)
    reference_terms = (
        "前面",
        "上面",
        "刚才",
        "这些",
        "整个方案",
        "整个架构",
        "最后",
        "this",
        "above",
        "previous",
        "the plan",
        "the architecture",
    )
    has_reference = any(term in text for term in reference_terms)
    return has_synthesis and has_reference
