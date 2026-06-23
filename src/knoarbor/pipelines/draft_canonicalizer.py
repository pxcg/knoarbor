from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.markdown import normalize_embedded_body_markdown, validate_body_markdown
from knoarbor.core.schemas.wiki_write import WikiDraft, WikiDraftInput, WikiPatchInput
from knoarbor.core.wiki_schema import normalize_page_dir
from knoarbor.retrieval.wiki_links import sanitize_unresolved_wikilinks
from knoarbor.storage.wiki_paths import normalize_page_title, normalize_source_digest_title


PLACEHOLDER_SOURCE_FILES = {"raw/source/path", "source/path", "raw/path"}


@dataclass(frozen=True)
class CanonicalizedDraft:
    draft: WikiDraft
    source_file: str | None
    changes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalizedContent:
    content: str
    removed_wikilinks: list[str] = field(default_factory=list)


class DraftCanonicalizer:
    """Turns model-produced drafts into writer-ready KnoArbor wiki drafts."""

    def canonicalize_draft(
        self,
        draft: WikiDraftInput,
        *,
        source_file: str | None,
        write_action: str,
    ) -> CanonicalizedDraft:
        changes: list[str] = []
        page_dir = normalize_page_dir(draft.page_dir)
        title = normalize_source_digest_title(draft.title) if page_dir == "sources" else normalize_page_title(draft.title)
        if title != draft.title:
            changes.append("normalized_title")

        resolved_source_file = self._canonical_source_file(source_file, write_action)
        if resolved_source_file != source_file:
            changes.append("normalized_source_file")

        summary = normalize_embedded_body_markdown(draft.summary, "summary")
        question = normalize_embedded_body_markdown(draft.question, "source context")
        answer = normalize_embedded_body_markdown(draft.answer, "answer")
        synthesis = normalize_embedded_body_markdown(draft.synthesis or draft.answer, "synthesis")
        if (summary, question, answer, synthesis) != (
            draft.summary,
            draft.question,
            draft.answer,
            draft.synthesis,
        ):
            changes.append("normalized_body_headings")

        patches = self._canonicalize_patches(draft.patches, changes)
        claims = [str(item).strip() for item in draft.claims if str(item).strip()][:12]
        entities = [str(item).strip() for item in draft.entities if str(item).strip()][:24]
        relations = [str(item).strip() for item in draft.relations if str(item).strip()][:12]
        evidence = [str(item).strip() for item in draft.evidence if str(item).strip()][:24]
        page_kind = _page_kind_from_draft(draft.page_kind, page_dir)
        page_role = _page_role_from_draft(draft.role, page_kind)
        subject_kind = _subject_kind_from_draft(draft.subject_kind, page_kind)
        facets = _identity_facets(draft.facets, page_dir, page_kind)

        canonical = WikiDraft(
            title=title,
            page_dir=page_dir,
            page_type="source" if page_role == "source_digest" else "page",
            canonical_path=draft.canonical_path or "",
            legacy_paths=draft.legacy_paths,
            page_kind=page_kind,
            subject_kind=subject_kind,
            role=page_role,
            facets=facets,
            question=question,
            answer=answer,
            summary=summary,
            definition="",
            claims=claims,
            entities=entities,
            relations=relations,
            evidence=evidence,
            synthesis=synthesis,
            key_points=[],
            tags=[],
            confidence=draft.confidence,
            model_provider=draft.model_provider,
            model_name=draft.model_name,
            patches=patches,
            source_digest_ids=draft.source_digest_ids,
            atom_ids=draft.atom_ids,
        )
        self.validate_draft(canonical, source_file=resolved_source_file, write_action=write_action)
        return CanonicalizedDraft(draft=canonical, source_file=resolved_source_file, changes=changes)

    def canonicalize_written_content(self, vault_path: Path, content: str) -> CanonicalizedContent:
        sanitized, removed = sanitize_unresolved_wikilinks(vault_path, content)
        return CanonicalizedContent(content=sanitized, removed_wikilinks=removed)

    def validate_draft(self, draft: WikiDraft, *, source_file: str | None, write_action: str) -> None:
        if write_action == "create" and not source_file:
            raise PolicyRejection("create requires source_file")
        if source_file and source_file.strip() in PLACEHOLDER_SOURCE_FILES:
            raise PolicyRejection(f"source_file is a placeholder, not provenance: {source_file}")
        validate_body_markdown(draft.summary, "summary")
        validate_body_markdown(draft.question, "source context")
        validate_body_markdown(draft.answer, "answer")
        validate_body_markdown(draft.synthesis, "synthesis")
        for claim in draft.claims:
            validate_body_markdown(claim, "claim")
        for entity in draft.entities:
            validate_body_markdown(entity, "entity")
        for relation in draft.relations:
            validate_body_markdown(relation, "relation")
        for evidence in draft.evidence:
            validate_body_markdown(evidence, "evidence")

    def _canonical_source_file(self, source_file: str | None, write_action: str) -> str | None:
        text = source_file.strip() if isinstance(source_file, str) else None
        if not text:
            return None if write_action in {"update", "merge"} else text
        return text

    def _canonicalize_patches(self, patches: list[WikiPatchInput], changes: list[str]) -> list[WikiPatchInput]:
        canonical: list[WikiPatchInput] = []
        for patch in patches:
            section = "Synthesis" if patch.section.strip().lower() == "answer" else patch.section
            if section != patch.section:
                changes.append("normalized_patch_section")
            content = patch.content
            heading = patch.heading
            if content:
                normalized_content = normalize_embedded_body_markdown(content, f"{patch.section} patch")
                if normalized_content != content:
                    changes.append("normalized_patch_headings")
                content = normalized_content
                validate_body_markdown(content, f"{patch.section} patch")
            if heading:
                heading = normalize_page_title(heading)
            canonical.append(patch.model_copy(update={"section": section, "content": content, "heading": heading}))
        return canonical


def _page_kind_from_draft(value: str, page_dir: str) -> str:
    text = _normalize_identity_value(value)
    if text:
        return text
    mapping = {
        "sources": "source_digest",
        "entities": "entity",
        "concepts": "concept",
        "comparisons": "comparison",
        "queries": "query",
        "timelines": "timeline",
        "workflows": "workflow",
    }
    return mapping.get(page_dir, "unknown")


def _page_role_from_draft(value: str, page_kind: str) -> str:
    text = _normalize_identity_value(value)
    if text:
        return text
    if page_kind == "source_digest":
        return "source_digest"
    if page_kind == "generated_view":
        return "generated_view"
    return "knowledge_page"


def _subject_kind_from_draft(value: str, page_kind: str) -> str:
    text = _normalize_identity_value(value)
    if text:
        return text
    return page_kind


def _identity_facets(explicit: list[str], page_dir: str, page_kind: str) -> list[str]:
    values = [*explicit, page_dir, page_kind]
    facets: list[str] = []
    for value in values:
        text = _normalize_identity_value(value)
        if text and text not in facets:
            facets.append(text)
    return facets


def _normalize_identity_value(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
