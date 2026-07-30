from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from knoarbor.core.evidence_alignment import align_evidence_quote
from knoarbor.core.schemas.index_metadata_extract import (
    ExtractedAmbiguity,
    ExtractedClaim,
    ExtractedEntity,
    ExtractedEvidenceQuote,
    ExtractedRelation,
    IndexMetadataExtractResult,
)
from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.source_record import SourceRecord
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.semantic.knowledge_atom_normalization import normalize_knowledge_atom_batch


def dominant_source_language(document: SourceDocument) -> str:
    return source_text_language(document_body(document))


def source_text_language(text: str) -> str:
    """Describe the source script without forcing bilingual text into one language."""

    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin_words = len(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text))
    if cjk and latin_words:
        if cjk >= 8 and latin_words < 4:
            return "zh"
        if latin_words >= 4 and cjk < 8:
            return "en"
        return "mixed"
    if cjk:
        return "zh"
    if latin_words:
        return "en"
    return "source"


@dataclass(frozen=True)
class IndexMetadataAtomCompilation:
    atom_batch: KnowledgeAtomBatch
    diagnostics: dict[str, object]
    ambiguities: list[ExtractedAmbiguity]


class EvidenceQuoteRejected(ValueError):
    def __init__(self, *, reason: str, quote_index: int, unit_position: int, quote: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.quote_index = quote_index
        self.unit_position = unit_position
        self.quote = quote


def compile_extracted_index_metadata(
    extracted: IndexMetadataExtractResult,
    *,
    source_record: SourceRecord,
    source_file: str,
) -> IndexMetadataAtomCompilation:
    extracted, diagnostics = _close_index_metadata_references(extracted, source_record, source_file)
    valid_unit_positions = set(range(len(source_record.units)))
    entity_by_position: dict[int, KnowledgeAtomObject] = {}
    rejected_entities = diagnostics.setdefault("rejected_entities", [])
    for entity_index, entity in enumerate(extracted.entities):
        invalid_positions = sorted(set(entity.unit_positions) - valid_unit_positions)
        if invalid_positions:
            rejected_entities.append(
                {
                    "entity_index": entity_index,
                    "entity_name": entity.name,
                    "unit_positions": invalid_positions,
                    "reason": "unknown_unit_position",
                }
            )
            continue
        evidence = _evidence_from_unit_positions(
            entity.unit_positions,
            source_record=source_record,
            source_file=source_file,
        )
        if not any(_name_is_explicit_in_text(entity.name, span.excerpt) for span in evidence):
            rejected_entities.append(
                {
                    "entity_index": entity_index,
                    "entity_name": entity.name,
                    "unit_positions": entity.unit_positions,
                    "reason": "name_not_explicit_in_cited_units",
                }
            )
            continue
        entity_by_position[entity_index] = _entity_to_atom(entity, evidence=evidence)
    entities = list(entity_by_position.values())
    accepted_claims: list[tuple[int, ExtractedClaim, KnowledgeClaim]] = []
    rejected_claims = diagnostics.setdefault("rejected_claims", [])
    rejected_relations = diagnostics.setdefault("rejected_relations", [])
    for claim_index, claim in enumerate(extracted.claims):
        try:
            atom = _claim_to_atom(
                claim,
                entity_names=_claim_entity_names(
                    claim,
                    claim_index=claim_index,
                    entity_by_position=entity_by_position,
                    diagnostics=diagnostics,
                ),
                source_record=source_record,
                source_file=source_file,
            )
        except EvidenceQuoteRejected as exc:
            rejected_claims.append(
                {
                    "claim_index": claim_index,
                    "quote_index": exc.quote_index,
                    "unit_position": exc.unit_position,
                    "quote": exc.quote,
                    "reason": exc.reason,
                }
            )
            rejected_relations.extend(
                {
                    "claim_index": claim_index,
                    "relation_index": relation_index,
                    "subject_entity_position": relation.subject_entity_position,
                    "predicate": relation.predicate,
                    "object_entity_position": relation.object_entity_position,
                    "reason": "parent_claim_rejected",
                }
                for relation_index, relation in enumerate(claim.relations)
            )
            continue
        accepted_claims.append((claim_index, claim, atom))
    claims = [atom for _, _, atom in accepted_claims]
    relations = _relations_to_atoms(
        accepted_claims,
        entity_by_position=entity_by_position,
        source_record=source_record,
        diagnostics=diagnostics,
    )
    synthesis = _synthesis_text(extracted.synthesis_topics) if claims or not extracted.claims else ""
    atom_batch = normalize_knowledge_atom_batch(
        KnowledgeAtomBatch(
            source_record_id=source_record.record_id,
            entities=entities,
            claims=claims,
            relations=relations,
            synthesis=synthesis,
        )
    )
    diagnostics["accepted"] = {
        "entities": len(atom_batch.entities),
        "claims": len(atom_batch.claims),
        "relations": len(atom_batch.relations),
        "aliases": sum(len(entity.aliases) for entity in atom_batch.entities),
        "claim_entity_references": sum(len(claim.entity_names) for claim in atom_batch.claims),
    }
    return IndexMetadataAtomCompilation(
        atom_batch=atom_batch,
        diagnostics=diagnostics,
        ambiguities=extracted.ambiguities,
    )


def _close_index_metadata_references(
    extracted: IndexMetadataExtractResult,
    source_record: SourceRecord,
    source_file: str,
) -> tuple[IndexMetadataExtractResult, dict[str, object]]:
    valid_unit_positions = set(range(len(source_record.units)))
    rejected_ambiguities: list[dict[str, object]] = []
    accepted_ambiguities: list[ExtractedAmbiguity] = []
    for ambiguity_index, ambiguity in enumerate(extracted.ambiguities):
        invalid_positions = sorted(set(ambiguity.unit_positions) - valid_unit_positions)
        if invalid_positions:
            rejected_ambiguities.append(
                {
                    "ambiguity_index": ambiguity_index,
                    "unit_positions": invalid_positions,
                    "reason": "unknown_unit_position",
                }
            )
            continue
        accepted_ambiguities.append(ambiguity)
    exact_names: dict[str, set[str]] = {}
    rejected_aliases: list[dict[str, object]] = []
    for entity in extracted.entities:
        exact_names.setdefault(_name_key(entity.name), set()).add(entity.name)

    entities = []
    for entity_index, entity in enumerate(extracted.entities):
        if set(entity.unit_positions) - valid_unit_positions:
            entities.append(entity)
            continue
        evidence = _evidence_from_unit_positions(entity.unit_positions, source_record=source_record, source_file=source_file)
        accepted_aliases: list[str] = []
        for alias in entity.aliases:
            key = _name_key(alias)
            if exact_names.get(key, set()) - {entity.name}:
                rejected_aliases.append(
                    {
                        "entity_index": entity_index,
                        "entity_name": entity.name,
                        "alias": alias,
                        "reason": "conflicts_with_declared_entity_name",
                    }
                )
                continue
            if not _alias_is_explicit_in_evidence(alias, evidence):
                rejected_aliases.append(
                    {
                        "entity_index": entity_index,
                        "entity_name": entity.name,
                        "alias": alias,
                        "reason": "not_explicit_in_cited_units",
                    }
                )
                continue
            accepted_aliases.append(alias)
        entities.append(entity.model_copy(update={"aliases": accepted_aliases}))

    rejected_relations: list[dict[str, object]] = []
    claims: list[ExtractedClaim] = []
    for claim_index, claim in enumerate(extracted.claims):
        accepted_relations: list[ExtractedRelation] = []
        relation_entity_positions: list[int] = []
        for relation_index, relation in enumerate(claim.relations):
            relation_details = {
                "claim_index": claim_index,
                "relation_index": relation_index,
                "subject_entity_position": relation.subject_entity_position,
                "predicate": relation.predicate,
                "object_entity_position": relation.object_entity_position,
            }
            if relation.subject_entity_position >= len(entities) or relation.object_entity_position >= len(entities):
                rejected_relations.append({**relation_details, "reason": "unknown_entity_position"})
                continue
            if relation.subject_entity_position == relation.object_entity_position:
                rejected_relations.append({**relation_details, "reason": "self_relation"})
                continue
            accepted_relations.append(relation)
            relation_entity_positions.extend([relation.subject_entity_position, relation.object_entity_position])

        entity_positions = list(dict.fromkeys([*claim.entity_positions, *relation_entity_positions]))
        claims.append(claim.model_copy(update={"entity_positions": entity_positions, "relations": accepted_relations}))

    diagnostics: dict[str, object] = {
        "candidates": {
            "entities": len(extracted.entities),
            "claims": len(extracted.claims),
            "relations": sum(len(claim.relations) for claim in extracted.claims),
            "aliases": sum(len(entity.aliases) for entity in extracted.entities),
            "claim_entity_references": sum(len(claim.entity_positions) for claim in extracted.claims),
        },
        "rejected_aliases": rejected_aliases,
        "rejected_ambiguities": rejected_ambiguities,
        "rejected_claim_entity_references": [],
        "rejected_relations": rejected_relations,
    }
    closed = extracted.model_copy(update={"entities": entities, "claims": claims, "ambiguities": accepted_ambiguities})
    return closed, diagnostics


def _claim_entity_names(
    claim: ExtractedClaim,
    *,
    claim_index: int,
    entity_by_position: dict[int, KnowledgeAtomObject],
    diagnostics: dict[str, object],
) -> list[str]:
    names: list[str] = []
    rejected = diagnostics.setdefault("rejected_claim_entity_references", [])
    for entity_position in claim.entity_positions:
        entity = entity_by_position.get(entity_position)
        if entity is None:
            rejected.append(
                {
                    "claim_index": claim_index,
                    "entity_index": entity_position,
                    "reason": "unknown_or_rejected_entity_position",
                }
            )
            continue
        names.append(entity.name)
    return list(dict.fromkeys(names))


def _name_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _synthesis_text(topics: list[str]) -> str:
    if len(topics) <= 1:
        return topics[0] if topics else ""
    return "\n".join(f"- {topic}" for topic in topics)


def document_body(document: SourceDocument) -> str:
    text = document.content.text.strip()
    if text:
        return text
    parts: list[str] = []
    for section in document.content.sections or []:
        title = str(section.get("title") or section.get("heading") or "").strip()
        content = str(section.get("content") or section.get("text") or "").strip()
        if title:
            parts.append(f"## {title}")
        if content:
            parts.append(content)
    return "\n\n".join(parts)


def _entity_to_atom(entity: ExtractedEntity, *, evidence: list[KnowledgeEvidenceSpan]) -> KnowledgeAtomObject:
    return KnowledgeAtomObject(
        object_type="knowledge_object",
        name=entity.name,
        aliases=entity.aliases,
        evidence=evidence,
    )


def _alias_is_explicit_in_evidence(alias: str, evidence: list[KnowledgeEvidenceSpan]) -> bool:
    return any(_name_is_explicit_in_text(alias, span.excerpt) for span in evidence)


def _name_is_explicit_in_text(name: str, text: str) -> bool:
    candidate = name.strip()
    if not candidate:
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", candidate):
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])", flags=re.IGNORECASE)
        return bool(pattern.search(text))
    return candidate.casefold() in text.casefold()


def _claim_to_atom(
    claim: ExtractedClaim,
    *,
    entity_names: list[str],
    source_record: SourceRecord,
    source_file: str,
) -> KnowledgeClaim:
    evidence = _claim_evidence_from_quotes(
        claim.evidence,
        source_record=source_record,
        source_file=source_file,
    )
    return KnowledgeClaim(
        id=_stable_atom_id("claim", source_record.record_id, claim.text, *(_evidence_identity(span) for span in evidence)),
        claim=claim.text,
        evidence=evidence,
        entity_names=entity_names,
    )


def _relations_to_atoms(
    accepted_claims: list[tuple[int, ExtractedClaim, KnowledgeClaim]],
    *,
    entity_by_position: dict[int, KnowledgeAtomObject],
    source_record: SourceRecord,
    diagnostics: dict[str, object],
) -> list[KnowledgeRelation]:
    grouped: dict[tuple[int, str, int], tuple[ExtractedRelation, list[int]]] = {}
    claims_by_index = {claim_index: claim for claim_index, _, claim in accepted_claims}
    for claim_index, extracted_claim, _ in accepted_claims:
        for relation in extracted_claim.relations:
            key = (relation.subject_entity_position, _name_key(relation.predicate), relation.object_entity_position)
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = (relation, [claim_index])
            else:
                existing[1].append(claim_index)

    output: list[KnowledgeRelation] = []
    for relation, claim_positions in grouped.values():
        subject = entity_by_position.get(relation.subject_entity_position)
        obj = entity_by_position.get(relation.object_entity_position)
        if subject is None or obj is None:
            diagnostics.setdefault("rejected_relations", []).append(
                {
                    "claim_indexes": claim_positions,
                    "subject_entity_position": relation.subject_entity_position,
                    "predicate": relation.predicate,
                    "object_entity_position": relation.object_entity_position,
                    "reason": "unknown_or_rejected_entity_position",
                }
            )
            continue
        source_claim_ids = [claims_by_index[position].id for position in claim_positions]
        evidence = _dedupe_evidence_for_claim_ids(source_claim_ids, list(claims_by_index.values()))
        output.append(
            KnowledgeRelation(
                id=_stable_atom_id(
                    "relation",
                    source_record.record_id,
                    subject.name,
                    relation.predicate,
                    obj.name,
                ),
                subject=KnowledgeAtomObject(name=subject.name),
                predicate=relation.predicate,
                object=KnowledgeAtomObject(name=obj.name),
                source_claim_ids=source_claim_ids,
                evidence=evidence,
            )
        )
    return output


def _evidence_from_unit_positions(
    unit_positions: list[int],
    *,
    source_record: SourceRecord,
    source_file: str,
) -> list[KnowledgeEvidenceSpan]:
    spans: list[KnowledgeEvidenceSpan] = []
    seen: set[tuple[int | None, str]] = set()
    for unit_position in unit_positions:
        if unit_position >= len(source_record.units):
            continue
        unit = source_record.units[unit_position]
        excerpt = unit.evidence.excerpt.strip()
        key = (unit.index, excerpt)
        if not excerpt or key in seen:
            continue
        seen.add(key)
        spans.append(
            unit.evidence.model_copy(
                update={
                    "source_record_id": source_record.record_id,
                    "source_path": source_file,
                    "source_unit_index": unit.index,
                    "excerpt": excerpt,
                }
            )
        )
    return spans


def _claim_evidence_from_quotes(
    evidence_quotes: list[ExtractedEvidenceQuote],
    *,
    source_record: SourceRecord,
    source_file: str,
) -> list[KnowledgeEvidenceSpan]:
    spans: list[KnowledgeEvidenceSpan] = []
    for quote_index, evidence_quote in enumerate(evidence_quotes):
        if evidence_quote.unit_position >= len(source_record.units):
            raise EvidenceQuoteRejected(
                reason="unknown_unit_position",
                quote_index=quote_index,
                unit_position=evidence_quote.unit_position,
                quote=evidence_quote.quote,
            )
        unit = source_record.units[evidence_quote.unit_position]
        source_text = unit.evidence.excerpt
        match = align_evidence_quote(source_text, evidence_quote.quote)
        if match is None:
            raise EvidenceQuoteRejected(
                reason="quote_not_found",
                quote_index=quote_index,
                unit_position=evidence_quote.unit_position,
                quote=evidence_quote.quote,
            )
        local_start, local_end = match.raw_start, match.raw_end
        excerpt = match.excerpt
        unit_start = unit.evidence.char_start or 0
        spans.append(
            unit.evidence.model_copy(
                update={
                    "source_record_id": source_record.record_id,
                    "source_path": source_file,
                    "source_unit_index": unit.index,
                    "excerpt": excerpt,
                    "excerpt_hash": sha256(excerpt.encode("utf-8")).hexdigest()[:12],
                    "char_start": unit_start + local_start,
                    "char_end": unit_start + local_end,
                }
            )
        )
    return spans


def _dedupe_evidence_for_claim_ids(source_claim_ids: list[str], claims: list[KnowledgeClaim]) -> list[KnowledgeEvidenceSpan]:
    spans: list[KnowledgeEvidenceSpan] = []
    seen: set[tuple[str, int | None, str]] = set()
    for claim in claims:
        if claim.id not in source_claim_ids:
            continue
        for span in claim.evidence:
            key = (span.source_record_id, span.source_unit_index, span.excerpt)
            if key not in seen:
                seen.add(key)
                spans.append(span)
    return spans


def _stable_atom_id(kind: str, *parts: str) -> str:
    normalized = "\0".join(" ".join(str(part).casefold().split()) for part in parts)
    return f"{kind}:" + sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _evidence_identity(span: KnowledgeEvidenceSpan) -> str:
    unit = span.source_unit_id or str(span.source_unit_index)
    location = f"{span.char_start}:{span.char_end}"
    content = span.excerpt_hash or span.excerpt
    return f"{unit}:{location}:{content}"
