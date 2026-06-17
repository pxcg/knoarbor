from __future__ import annotations

import re
from dataclasses import dataclass

from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.chat import ChatSessionRecord, ChatTopicAnchor, ChatTopicRelation, ChatToolTraceItem


_KNOWN_ENTITIES = (
    "Agent Loop",
    "Workflow",
    "OpenClaw",
    "MCP",
    "Model Context Protocol",
    "JSON-RPC",
    "A2A",
    "Agent-to-Agent",
    "Memory",
    "Routing",
    "Multi-Agent",
    "KnoArbor",
    "LLM-Wiki",
    "RAG",
    "WeKnora",
    "FastQA",
    "SmartReasoning",
    "DataAnalyst",
    "Claude Code",
    "Codex",
    "Ollama",
    "vLLM",
    "Qwen",
    "DeepSeek",
    "iOS",
)


@dataclass(frozen=True)
class ChatTopicAnchorBuilder:
    """Builds a soft, updateable focus for multi-turn wiki chat."""

    def build(
        self,
        latest_user: str,
        *,
        existing_session: ChatSessionRecord | None = None,
        observations: list[ChatToolTraceItem] | None = None,
    ) -> ChatTopicAnchor:
        prior = existing_session.topic_anchor if existing_session else None
        prior_entities = list(prior.key_entities) if prior else []
        extracted = _extract_entities(latest_user)
        evidence_entities = _entities_from_observations(observations or [])
        relation = _relation_to_previous(latest_user, prior, extracted)
        entities = _unique([*extracted, *prior_entities, *evidence_entities])[:12]
        if relation == "switch":
            entities = _unique([*extracted, *evidence_entities])[:12] or entities[:6]
        topic = _active_topic(latest_user, prior, relation, entities)
        goal = _active_goal(latest_user, prior, relation)
        excluded = _excluded_directions(latest_user, topic, entities)
        return ChatTopicAnchor(
            active_topic=topic,
            active_goal=goal,
            key_entities=entities,
            recent_answer_type="",
            relation_to_previous=relation,
            excluded_directions=excluded,
        )


def update_anchor_after_evidence(anchor: ChatTopicAnchor, observations: list[ChatToolTraceItem]) -> ChatTopicAnchor:
    """Add evidence-derived entities after retrieval without changing relation."""

    entities = _unique([*anchor.key_entities, *_entities_from_observations(observations)])[:12]
    return anchor.model_copy(update={"key_entities": entities})


def update_anchor_answer_type(anchor: ChatTopicAnchor, observations: list[ChatToolTraceItem]) -> ChatTopicAnchor:
    answer_type = _answer_type_from_observations(observations)
    if not answer_type:
        return anchor
    return anchor.model_copy(update={"recent_answer_type": answer_type})


def _relation_to_previous(latest_user: str, prior: ChatTopicAnchor | None, extracted: list[str]) -> ChatTopicRelation:
    text = latest_user.strip().lower()
    if not prior or not prior.active_topic:
        return "switch"
    if _has_any(text, _SYNTHESIS_TERMS) and _has_any(text, _PRIOR_REFERENCE_TERMS):
        return "synthesize"
    if _has_any(text, _REFINE_TERMS):
        return "refine"
    overlap = set(_normalize_entity(item) for item in extracted) & set(_normalize_entity(item) for item in prior.key_entities)
    if overlap:
        return "continue"
    if _looks_like_followup(latest_user):
        return "continue"
    if extracted and _has_any(text, _SIDE_QUESTION_TERMS) and len(text) <= 80 and _is_side_question(latest_user, prior, extracted):
        return "side_question"
    if len(text) <= 50 and not extracted and _has_any(text, _PRONOUN_TERMS):
        return "continue"
    return "switch"


def _active_topic(latest_user: str, prior: ChatTopicAnchor | None, relation: ChatTopicRelation, entities: list[str]) -> str:
    if relation in {"continue", "refine", "synthesize", "side_question"} and prior and prior.active_topic:
        return prior.active_topic
    if entities:
        return " / ".join(entities[:4])
    return compact_inline_text(latest_user, 80)


def _active_goal(latest_user: str, prior: ChatTopicAnchor | None, relation: ChatTopicRelation) -> str:
    if relation in {"continue", "refine", "synthesize", "side_question"} and prior and prior.active_goal:
        return prior.active_goal
    return compact_inline_text(latest_user, 160)


def _extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    lowered = text.lower()
    for entity in _KNOWN_ENTITIES:
        if entity.lower() in lowered:
            entities.append(entity)
    entities.extend(_extract_capitalized_phrases(text))
    entities.extend(_extract_chinese_terms(text))
    return _unique(entities)


def _extract_capitalized_phrases(text: str) -> list[str]:
    phrases = re.findall(r"\b[A-Z][A-Za-z0-9+-]*(?:[-\s][A-Z][A-Za-z0-9+-]*){0,4}\b", text)
    ignored = {"I", "A", "The", "This", "What", "How", "If", "And", "Or"}
    return [phrase.strip() for phrase in phrases if phrase.strip() not in ignored and len(phrase.strip()) > 1]


def _extract_chinese_terms(text: str) -> list[str]:
    terms = []
    for term in ("意图识别", "多路由调度", "记忆系统", "长期记忆", "短期记忆", "工具调用", "工程化", "知识库", "知识图谱"):
        if term in text:
            terms.append(term)
    return terms


def _entities_from_observations(observations: list[ChatToolTraceItem]) -> list[str]:
    entities: list[str] = []
    for item in observations[-6:]:
        for citation in item.citations:
            entities.extend(_extract_entities(" ".join(part for part in (citation.title or "", citation.path or "") if part)))
        pack = item.result.get("evidence_pack")
        if not isinstance(pack, dict):
            continue
        for key in ("primary_pages", "supporting_pages", "source_pages", "citation_pages"):
            pages = pack.get(key) if isinstance(pack.get(key), list) else []
            for page in pages:
                if isinstance(page, dict):
                    entities.extend(_extract_entities(" ".join(str(page.get(part) or "") for part in ("title", "path", "summary"))))
        primary = pack.get("primary_page")
        if isinstance(primary, dict):
            entities.extend(_extract_entities(" ".join(str(primary.get(part) or "") for part in ("title", "path", "summary"))))
    return _unique(entities)


def _answer_type_from_observations(observations: list[ChatToolTraceItem]) -> str:
    for item in reversed(observations):
        pack = item.result.get("evidence_pack")
        if isinstance(pack, dict) and pack.get("answer_type"):
            return str(pack["answer_type"])
    return ""


def _excluded_directions(latest_user: str, topic: str, entities: list[str]) -> list[str]:
    text = f"{latest_user} {topic}".lower()
    if "agent" not in text and "openclaw" not in text:
        return []
    excluded = []
    for item in ("WeKnora", "FastQA", "SmartReasoning", "DataAnalyst"):
        if item.lower() not in text and all(item.lower() != entity.lower() for entity in entities):
            excluded.append(item)
    return excluded


def _normalize_entity(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _looks_like_followup(text: str) -> bool:
    lowered = text.strip().lower()
    return _has_any(lowered, _PRONOUN_TERMS) or _has_any(lowered, _FOLLOWUP_TERMS)


def _is_side_question(text: str, prior: ChatTopicAnchor, extracted: list[str]) -> bool:
    lowered = text.lower()
    if _has_any(lowered, ("顺便", "另外", "插一句", "side question", "by the way")):
        return True
    prior_keys = {_normalize_entity(item) for item in prior.key_entities}
    if not prior_keys & _AGENT_RELATED_ENTITY_KEYS:
        return False
    extracted_keys = {_normalize_entity(item) for item in extracted}
    return bool(extracted_keys & _AGENT_RELATED_ENTITY_KEYS)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = re.sub(r"\s+", " ", value).strip(" -_")
        key = _normalize_entity(item)
        if not item or not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


_SYNTHESIS_TERMS = (
    "总结",
    "整理",
    "汇总",
    "归纳",
    "方案",
    "大纲",
    "路线图",
    "设计文档",
    "outline",
    "roadmap",
    "summarize",
    "synthesis",
)
_PRIOR_REFERENCE_TERMS = (
    "前面",
    "上面",
    "刚才",
    "这些",
    "以上",
    "整个",
    "整体",
    "最后",
    "previous",
    "above",
    "this plan",
    "the plan",
)
_REFINE_TERMS = (
    "展开",
    "详细",
    "细讲",
    "举例",
    "具体",
    "深入",
    "第二点",
    "第三点",
    "这一点",
    "这个点",
    "explain more",
    "more detail",
    "elaborate",
)
_FOLLOWUP_TERMS = ("那么", "那", "这里", "里面", "这个", "这种", "它", "其", "this", "that", "it")
_PRONOUN_TERMS = ("它", "其", "这个", "这种", "这里", "里面", "this", "that", "it", "they", "them")
_SIDE_QUESTION_TERMS = ("是什么", "什么是", "关系", "区别", "怎么", "如何", "what", "how", "difference", "relationship")
_AGENT_RELATED_ENTITY_KEYS = {
    _normalize_entity(item)
    for item in (
        "Agent Loop",
        "Workflow",
        "OpenClaw",
        "MCP",
        "Model Context Protocol",
        "JSON-RPC",
        "A2A",
        "Agent-to-Agent",
        "Memory",
        "Routing",
        "Multi-Agent",
    )
}
