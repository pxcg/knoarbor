from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knoarbor.core.schemas.chat import ChatSessionRecord, ChatToolPlan, ChatToolTraceItem


@dataclass(frozen=True)
class ChatEvidenceAssessment:
    """Evidence sufficiency decision for the current chat turn."""

    sufficient: bool
    reason: str
    recommended_next_step: str


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
        followup_adjustment = self._adjust_broad_anchor_followup(plan, query=query, observations=observations)
        if followup_adjustment:
            return followup_adjustment
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

    def assess_evidence(self, observations: list[ChatToolTraceItem], *, query: str) -> ChatEvidenceAssessment:
        if not observations:
            return ChatEvidenceAssessment(False, "no_observations", "query_wiki")
        if any(item.status == "error" for item in observations):
            return ChatEvidenceAssessment(False, "tool_error", "retry_or_refine_tool")

        successful_reads = [item for item in observations if item.tool == "read_wiki_page" and item.status == "ok"]
        evidence_packs = [item.result.get("evidence_pack") for item in observations if isinstance(item.result.get("evidence_pack"), dict)]

        if successful_reads and not evidence_packs:
            if _allows_single_page_read(query):
                return ChatEvidenceAssessment(True, "explicit_page_read", "finish_answer")
            if _is_broad_knowledge_request(query):
                return ChatEvidenceAssessment(False, "anchor_page_needs_supporting_evidence", "query_wiki")
            return ChatEvidenceAssessment(True, "single_page_read", "finish_answer")

        for pack in evidence_packs:
            if not isinstance(pack, dict):
                continue
            coverage = pack.get("evidence_coverage") if isinstance(pack.get("evidence_coverage"), dict) else {}
            if pack.get("recommended_action") != "answer_from_evidence":
                return ChatEvidenceAssessment(False, "pack_recommends_more_evidence", _recommended_step_from_pack(pack))
            if coverage.get("status") == "weak":
                return ChatEvidenceAssessment(False, "weak_coverage", "query_wiki")
            if not pack.get("primary_pages") and not pack.get("primary_page"):
                return ChatEvidenceAssessment(False, "missing_primary_page", "query_wiki")

        return ChatEvidenceAssessment(True, "evidence_pack_sufficient", "finish_answer")

    def _adjust_broad_anchor_followup(
        self,
        plan: ChatToolPlan,
        *,
        query: str,
        observations: list[ChatToolTraceItem],
    ) -> tuple[ChatToolPlan, ChatPlanAdjustment] | None:
        if _allows_single_page_read(query):
            return None
        if not _is_broad_knowledge_request(query):
            return None
        if not observations:
            return None
        if not any(call.name == "finish_answer" for call in plan.tool_calls):
            return None
        if any(isinstance(item.result.get("evidence_pack"), dict) for item in observations):
            return None
        anchor_paths = [
            str(item.result.get("path") or "")
            for item in observations
            if item.tool == "read_wiki_page" and item.status == "ok" and item.result.get("path")
        ]
        if not anchor_paths:
            return None
        adjusted = ChatToolPlan(
            tool_calls=[
                {
                    "name": "query_wiki",
                    "arguments": {
                        "query": query,
                        "mode": "deep",
                        "max_results": 8,
                    },
                }
            ],
            reason="Broad knowledge questions may use the anchor page, but need supporting wiki evidence before final synthesis.",
            confidence=max(plan.confidence, 0.85),
        )
        return adjusted, ChatPlanAdjustment(
            kind="anchor_page_needs_supporting_evidence",
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


def _recommended_step_from_pack(pack: dict[str, Any]) -> str:
    action = str(pack.get("recommended_action") or "")
    if action == "read_primary_if_detail_needed":
        return "read_wiki_page"
    return "query_wiki"


def _allows_single_page_read(query: str) -> bool:
    text = query.strip().lower()
    if not text:
        return False
    explicit_terms = (
        "全文",
        "完整页面",
        "完整内容",
        "打开页面",
        "读取页面",
        "读一下",
        "展开这个页面",
        "这个页面",
        "该页面",
        "page content",
        "full page",
        "read this page",
        "open this page",
    )
    source_terms = (
        "参考页面",
        "来源",
        "引用",
        "依据",
        "原文",
        "材料",
        "source",
        "reference",
        "citation",
        "raw material",
    )
    return any(term in text for term in explicit_terms) or any(term in text for term in source_terms)


def _is_followup_detail_request(query: str) -> bool:
    text = query.strip().lower()
    detail_terms = (
        "展开",
        "详细",
        "细讲",
        "举例",
        "具体",
        "第二点",
        "第三点",
        "这一点",
        "这个点",
        "explain more",
        "more detail",
        "elaborate",
    )
    return any(term in text for term in detail_terms)


def _is_broad_knowledge_request(query: str) -> bool:
    text = query.strip().lower()
    if not text:
        return False
    broad_terms = (
        "架构",
        "系统",
        "框架",
        "方案",
        "设计",
        "模块",
        "几个方面",
        "哪些",
        "区别",
        "对比",
        "关系",
        "如何",
        "怎么",
        "生产",
        "工程",
        "路线",
        "综合",
        "整理",
        "总结",
        "architecture",
        "system",
        "framework",
        "design",
        "module",
        "compare",
        "difference",
        "relationship",
        "production",
        "roadmap",
        "synthesize",
    )
    if any(term in text for term in broad_terms):
        return True
    return len(text) > 80


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
