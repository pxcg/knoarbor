from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class BM25Field:
    name: str
    text: str
    weight: float = 1.0


@dataclass(frozen=True)
class BM25Document:
    id: str
    fields: list[BM25Field]


@dataclass
class BM25Match:
    score: float
    matched_fields: set[str]
    matched_terms: dict[str, list[str]]


def score_bm25_documents(
    documents: list[BM25Document],
    terms: list[str],
    query: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[str, BM25Match]:
    """Score page-like documents with field-weighted BM25.

    Terms are supplied by KnoArbor's query normalizer. Field text is tokenized
    for length normalization and scanned by normalized substring occurrence so
    CJK bigrams/trigrams and technical identifiers both work without a model.
    """

    if not documents or not terms:
        return {}

    normalized_terms = _unique_terms(terms)
    field_lengths = _field_lengths(documents)
    average_lengths = _average_field_lengths(field_lengths)
    document_frequencies = _document_frequencies(documents, normalized_terms)
    total_documents = len(documents)
    phrase = _normalize_text(query)

    matches: dict[str, BM25Match] = {}
    for document in documents:
        score = 0.0
        matched_fields: set[str] = set()
        matched_terms: dict[str, list[str]] = {}
        for field in document.fields:
            field_text = _normalize_text(field.text)
            if not field_text:
                continue
            term_counts = _term_counts(field_text, normalized_terms)
            if not term_counts and not _phrase_match(field_text, phrase):
                continue
            field_score = 0.0
            field_length = max(1, field_lengths[document.id].get(field.name, 1))
            average_length = max(1.0, average_lengths.get(field.name, 1.0))
            for term, frequency in term_counts.items():
                df = document_frequencies.get(field.name, {}).get(term, 0)
                if df <= 0:
                    continue
                idf = math.log(1.0 + (total_documents - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (1.0 - b + b * (field_length / average_length))
                field_score += idf * (frequency * (k1 + 1.0)) / denominator
            if _phrase_match(field_text, phrase):
                field_score += 1.5
                term_counts.setdefault(phrase, 1)
            if field_score <= 0:
                continue
            matched_fields.add(field.name)
            matched_terms[field.name] = list(term_counts)[:12]
            score += field_score * field.weight
        if score > 0:
            matches[document.id] = BM25Match(score=score, matched_fields=matched_fields, matched_terms=matched_terms)
    return matches


def _field_lengths(documents: list[BM25Document]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for document in documents:
        output[document.id] = {}
        for field in document.fields:
            output[document.id][field.name] = len(_tokens(field.text))
    return output


def _average_field_lengths(field_lengths: dict[str, dict[str, int]]) -> dict[str, float]:
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for lengths in field_lengths.values():
        for field, length in lengths.items():
            totals[field] = totals.get(field, 0) + max(1, length)
            counts[field] = counts.get(field, 0) + 1
    return {field: totals[field] / counts[field] for field in totals}


def _document_frequencies(documents: list[BM25Document], terms: list[str]) -> dict[str, dict[str, int]]:
    frequencies: dict[str, dict[str, int]] = {}
    for document in documents:
        for field in document.fields:
            field_text = _normalize_text(field.text)
            if not field_text:
                continue
            field_frequency = frequencies.setdefault(field.name, {})
            for term in terms:
                if term in field_text:
                    field_frequency[term] = field_frequency.get(term, 0) + 1
    return frequencies


def _term_counts(text: str, terms: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    token_counts = Counter(_tokens(text))
    for term in terms:
        if not term:
            continue
        frequency = token_counts.get(term, 0)
        if frequency <= 0 and term in text:
            frequency = text.count(term)
        if frequency > 0:
            counts[term] = frequency
    return counts


def _tokens(value: str) -> list[str]:
    text = _normalize_text(value)
    tokens = re.findall(r"[a-z0-9][a-z0-9_.+-]{1,}", text)
    for group in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.extend(group[index : index + 2] for index in range(0, max(len(group) - 1, 0)))
        if len(group) >= 3:
            tokens.extend(group[index : index + 3] for index in range(0, len(group) - 2))
    return tokens


def _phrase_match(text: str, phrase: str) -> bool:
    return len(phrase) >= 3 and phrase in text


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for term in terms:
        text = _normalize_text(term)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()

