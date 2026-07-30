from __future__ import annotations

from collections.abc import Callable

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeEvidenceSpan


EvidenceMapper = Callable[[KnowledgeEvidenceSpan], KnowledgeEvidenceSpan]


def map_knowledge_evidence(batch: KnowledgeAtomBatch, mapper: EvidenceMapper) -> KnowledgeAtomBatch:
    """Apply one evidence transformation across every knowledge atom kind."""

    entities = [entity.model_copy(update={"evidence": [mapper(span) for span in entity.evidence]}) for entity in batch.entities]
    claims = [claim.model_copy(update={"evidence": [mapper(span) for span in claim.evidence]}) for claim in batch.claims]
    relations = [relation.model_copy(update={"evidence": [mapper(span) for span in relation.evidence]}) for relation in batch.relations]
    return batch.model_copy(update={"entities": entities, "claims": claims, "relations": relations})
