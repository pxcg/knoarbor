from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.markdown import normalize_embedded_body_markdown, validate_body_markdown
from knoarbor.core.schemas.wiki_write import WikiDraft, WikiDraftInput, WikiPatchInput
from knoarbor.core.wiki_schema import frontmatter_type, normalize_page_dir
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
        question = normalize_embedded_body_markdown(draft.question, "source focus")
        answer = normalize_embedded_body_markdown(draft.answer, "answer")
        if (summary, question, answer) != (draft.summary, draft.question, draft.answer):
            changes.append("normalized_body_headings")

        patches = self._canonicalize_patches(draft.patches, changes)
        key_points = [str(item).strip() for item in draft.key_points if str(item).strip()][:8]
        tags = [str(item).strip().lower().replace(" ", "-") for item in draft.tags if str(item).strip()][:8]

        canonical = WikiDraft(
            title=title,
            page_dir=page_dir,
            page_type=frontmatter_type(page_dir),
            question=question,
            answer=answer,
            summary=summary,
            key_points=key_points,
            tags=tags,
            confidence=draft.confidence,
            model_provider=draft.model_provider,
            model_name=draft.model_name,
            patches=patches,
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
        validate_body_markdown(draft.question, "source focus")
        validate_body_markdown(draft.answer, "answer")

    def _canonical_source_file(self, source_file: str | None, write_action: str) -> str | None:
        text = source_file.strip() if isinstance(source_file, str) else None
        if not text:
            return None if write_action in {"update", "merge"} else text
        return text

    def _canonicalize_patches(self, patches: list[WikiPatchInput], changes: list[str]) -> list[WikiPatchInput]:
        canonical: list[WikiPatchInput] = []
        for patch in patches:
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
            canonical.append(patch.model_copy(update={"content": content, "heading": heading}))
        return canonical
