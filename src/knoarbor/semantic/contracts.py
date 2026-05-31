from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from pydantic import BaseModel

from knoarbor.core.errors import SemanticContractError
from knoarbor.core.schemas.ingest_review import IngestDraftReview
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_relation_plan import WikiRelationPlan


@dataclass(frozen=True)
class SemanticContract:
    name: str
    schema_version: str
    schema_model: type[BaseModel]
    prompt_name: str
    prompt_text: str


@lru_cache(maxsize=16)
def load_semantic_contract(name: str) -> SemanticContract:
    registry: dict[str, tuple[str, type[BaseModel], str]] = {
        "source_normalize": ("knowledge_extract.v1", KnowledgeExtract, "source_normalize_agent.md"),
        "wiki_relation": ("wiki_relation_plan.v1", WikiRelationPlan, "wiki_relation_agent.md"),
        "wiki_draft_compile": ("wiki_draft_batch.v1", WikiDraftBatch, "wiki_draft_compile_agent.md"),
        "ingest_draft_review": ("ingest_draft_review.v2", IngestDraftReview, "ingest_draft_review_agent.md"),
        "lint_diagnose": ("maintenance_candidates.v1", MaintenanceCandidates, "lint_diagnose_agent.md"),
        "lint_quality_diagnose": ("maintenance_candidates.v1", MaintenanceCandidates, "lint_quality_diagnose_agent.md"),
        "lint_maintenance_review": (
            "lint_maintenance_review.v1",
            LintMaintenanceReview,
            "lint_maintenance_review_agent.md",
        ),
        "lint_draft_compile": ("wiki_draft_batch.v1", WikiDraftBatch, "lint_draft_compile_agent.md"),
    }
    if name in registry:
        schema_version, schema_model, prompt_name = registry[name]
        return SemanticContract(
            name=name,
            schema_version=schema_version,
            schema_model=schema_model,
            prompt_name=prompt_name,
            prompt_text=load_prompt(prompt_name),
        )
    raise SemanticContractError(f"Unknown semantic contract: {name}")


def load_prompt(prompt_name: str) -> str:
    prompt_path = resources.files("knoarbor.semantic.prompts").joinpath(prompt_name)
    return prompt_path.read_text(encoding="utf-8")
