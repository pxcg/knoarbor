from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knoarbor.core.schemas.wiki_relation_plan import WikiPageDir
from knoarbor.core.schemas.wiki_write import WikiPatchInput, WikiWriteAction


class WikiDraftBatchItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    operation_index: int = Field(..., ge=0)
    write_action: WikiWriteAction
    target_page: str | None = None
    source_file: str | None = None
    title: str = Field(..., min_length=1)
    page_dir: WikiPageDir
    page_kind: str = ""
    subject_kind: str = ""
    facets: list[str] = Field(default_factory=list)
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    definition: str = ""
    claims: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    synthesis: str = ""
    key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)
    patches: list[WikiPatchInput] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
    model_provider: str = Field(default="external", min_length=1)
    model_name: str = Field(default="semantic-workflow", min_length=1)

    @field_validator("target_page", "source_file")
    @classmethod
    def blank_optional_text_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("facets", "source_digest_ids", "atom_ids", mode="before")
    @classmethod
    def normalize_id_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        ids: list[str] = []
        for item in value if isinstance(value, list) else []:
            text = str(item).strip()
            if text and text not in ids:
                ids.append(text)
        return ids

    @model_validator(mode="after")
    def fill_evidence_page_fields(self) -> WikiDraftBatchItem:
        if not self.definition.strip():
            self.definition = self.summary
        if not self.synthesis.strip():
            self.synthesis = self.answer
        if not self.claims:
            self.claims = list(self.key_points)
        return self

    @model_validator(mode="after")
    def validate_write_action(self) -> WikiDraftBatchItem:
        if self.write_action == "create" and self.target_page:
            raise ValueError("create draft must not set target_page")
        if self.write_action in {"update", "merge"}:
            if not self.target_page:
                raise ValueError(f"{self.write_action} draft requires target_page")
            if not self.patches:
                raise ValueError(f"{self.write_action} draft requires patches")
        return self


class WikiDraftBatch(BaseModel):
    drafts: list[WikiDraftBatchItem] = Field(default_factory=list)
    batch_summary: str = Field(..., min_length=1)
    warnings: list[str] = Field(default_factory=list)
