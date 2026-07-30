from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


QUERY_STOP_TERMS = {
    "a",
    "an",
    "about",
    "answer",
    "are",
    "based",
    "by",
    "did",
    "do",
    "does",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "is",
    "list",
    "of",
    "on",
    "please",
    "show",
    "summarize",
    "tell",
    "the",
    "to",
    "versus",
    "vs",
    "was",
    "were",
    "what",
    "which",
    "with",
    "why",
    "一下",
    "一些",
    "什么",
    "介绍",
    "列出",
    "哪些",
    "基于",
    "如何",
    "怎么",
    "我想",
    "所有",
    "按照",
    "相关",
    "知识",
    "知识库",
    "给出",
    "这个",
    "这些",
    "这是",
    "这里",
    "其中",
}

QUERY_STOP_SUBSTRINGS = (
    "是什么",
    "是什",
    "什么是",
    "为我",
    "帮我",
    "请",
    "请按",
    "知识库里",
    "和我说",
    "告诉我",
)

_CJK_QUERY_BOUNDARY = re.compile(
    "|".join(
        re.escape(value)
        for value in sorted(
            {
                "请基于我的知识库回答",
                "基于我的知识库",
                "这是什么样的",
                "这是什么",
                "这是",
                "这个",
                "这些",
                "这套",
                "这里",
                "其中",
                "是哪本书",
                "哪本书",
                "有什么",
                "介绍一下",
                "讲解一下",
                "用一句话解释",
                "一句话解释",
                "概述一下",
                "总结一下",
                "告诉我",
                "知识库里",
                "是什么",
                "有哪些",
                "有多少",
                "是多少",
                "是哪个",
                "为什么",
                "请帮我",
                "知识库",
                "并且",
                "或者",
                "还是",
                "请问",
                "帮我",
                "如何",
                "怎么",
                "怎样",
                "哪些",
                "什么",
                "中的",
                "多少",
                "是谁",
                "为何",
                "回答",
                "解释",
                "基于",
                "以及",
                "的",
                "和",
                "与",
                "及",
                "由",
                "谁",
                "吗",
                "呢",
                "吧",
                "请",
            },
            key=len,
            reverse=True,
        )
    )
)

@dataclass(frozen=True)
class TechnicalAnchor:
    variants: tuple[str, ...]
    parts: tuple[str, ...]


@dataclass(frozen=True)
class LexicalQueryPlan:
    terms: tuple[str, ...]
    cjk_anchors: tuple[str, ...]
    latin_anchor_groups: tuple[tuple[str, ...], ...]
    technical_anchors: tuple[TechnicalAnchor, ...]


def query_terms(query: str) -> list[str]:
    return list(build_lexical_query_plan(query).terms)


def build_lexical_query_plan(query: str) -> LexicalQueryPlan:
    scan_text = unicodedata.normalize("NFKC", query)
    terms: list[str] = []
    latin_groups: list[tuple[str, ...]] = []
    technical_anchors: list[TechnicalAnchor] = []
    for identifier in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", scan_text):
        variants = tuple(term for term in identifier_variants(identifier) if _is_query_signal_term(term))
        if not variants:
            continue
        latin_groups.append(variants)
        terms.extend(variants)
        if _is_technical_identifier(identifier):
            technical_anchors.append(TechnicalAnchor(variants=variants, parts=tuple(_identifier_parts(identifier))))
    cjk_anchors = _cjk_query_anchors(query)
    for anchor in cjk_anchors:
        terms.extend(_cjk_terms(anchor))
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if _is_query_signal_term(term) and term not in seen:
            seen.add(term)
            unique.append(term)
    return LexicalQueryPlan(
        terms=tuple(unique),
        cjk_anchors=tuple(cjk_anchors),
        latin_anchor_groups=tuple(latin_groups),
        technical_anchors=tuple(technical_anchors),
    )


def lexical_tokens(value: str) -> list[str]:
    """Return the deterministic index/query token stream.

    CJK bigrams are primary recall tokens. Trigrams and the full phrase remain
    available to BM25 ranking without becoming a second eligibility system.
    """

    normalized = normalize_text(value)
    scan_text = unicodedata.normalize("NFKC", value)
    output: list[str] = []
    for identifier in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", scan_text):
        output.extend(identifier_variants(identifier))
    for group in re.findall(r"[\u3400-\u9fff]+", normalized):
        if len(group) == 1:
            output.append(group)
            continue
        output.extend(group[index : index + 2] for index in range(len(group) - 1))
        if len(group) >= 3:
            output.extend(group[index : index + 3] for index in range(len(group) - 2))
        output.append(group)
    return _dedupe(output)


def identifier_variants(value: str) -> list[str]:
    original = normalize_text(value)
    if not original:
        return []
    parts = _identifier_parts(value)
    variants = [original, *parts]
    if len(parts) > 1:
        variants.extend(["".join(parts), "_".join(parts), "-".join(parts)])
    return _dedupe(variants)


def _identifier_parts(value: str) -> list[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", unicodedata.normalize("NFKC", value))
    separated = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", separated)
    separated = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", separated).lower()
    return [part for part in re.split(r"[\s_.+\-/]+", separated) if part]


def _is_query_signal_term(term: str) -> bool:
    text = term.strip().lower()
    if not text or text in QUERY_STOP_TERMS:
        return False
    return not any(fragment in text for fragment in QUERY_STOP_SUBSTRINGS)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _cjk_query_anchors(query: str) -> list[str]:
    normalized = normalize_text(query)
    anchors: list[str] = []
    for group in re.findall(r"[\u3400-\u9fff]+", normalized):
        for segment in _CJK_QUERY_BOUNDARY.split(group):
            text = segment.strip()
            if len(text) >= 2 and text not in QUERY_STOP_TERMS and text not in anchors:
                anchors.append(text)
    return anchors


def _cjk_terms(anchor: str) -> list[str]:
    terms = [anchor]
    if len(anchor) >= 2:
        terms.extend(anchor[index : index + 2] for index in range(len(anchor) - 1))
    if len(anchor) >= 3:
        terms.extend(anchor[index : index + 3] for index in range(len(anchor) - 2))
    return terms


def _is_technical_identifier(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value)
    return bool(
        any(character.isdigit() for character in normalized)
        or any(character in "_.+-" for character in normalized)
        or re.search(r"[a-z0-9][A-Z]", normalized)
        or (len(normalized) >= 3 and normalized.isupper())
    )
