from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.markdown import (
    append_to_section,
    extract_list_items,
    extract_section,
    normalize_embedded_body_markdown,
    parse_frontmatter,
    replace_section,
    update_heading,
    update_frontmatter_value,
    validate_body_markdown,
)


class CoreMarkdownTests(unittest.TestCase):
    def test_parse_and_update_frontmatter(self) -> None:
        content = "---\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n# Page\n"
        updated = update_frontmatter_value(content, "updated", "2026-01-02")

        self.assertEqual(parse_frontmatter(updated)["updated"], "2026-01-02")

    def test_replace_and_append_section(self) -> None:
        content = "# Page\n\n## Summary\n\nOld.\n"
        replaced = replace_section(content, "Summary", "New.")
        appended = append_to_section(replaced, "Notes", "First note.")

        self.assertEqual(extract_section(replaced, "Summary"), "New.")
        self.assertEqual(extract_section(appended, "Notes"), "First note.")

    def test_replacements_preserve_regex_escape_sequences_as_text(self) -> None:
        content = "---\ncreated: 2026-01-01\n---\n# Old\n\n## Synthesis\n\nOld.\n"

        updated = update_frontmatter_value(content, "content_hash", r"model_\metadata")
        updated = update_heading(updated, r"Model \metadata")
        updated = replace_section(updated, "Synthesis", r"Use \m and \alpha as literal Markdown text.")

        self.assertEqual(parse_frontmatter(updated)["content_hash"], r"model_\metadata")
        self.assertIn(r"# Model \metadata", updated)
        self.assertEqual(extract_section(updated, "Synthesis"), r"Use \m and \alpha as literal Markdown text.")

    def test_empty_section_does_not_capture_next_heading(self) -> None:
        content = "# Page\n\n## Evidence\n\n\n## Synthesis\n\nAgent notes.\n"
        replaced = replace_section(content, "Evidence", "- raw/inbox/notes/source.md")

        self.assertEqual(extract_section(content, "Evidence"), "")
        self.assertEqual(extract_section(content, "Synthesis"), "Agent notes.")
        self.assertIn("## Evidence\n\n- raw/inbox/notes/source.md\n## Synthesis", replaced)

    def test_extract_list_items_ignores_empty_placeholders(self) -> None:
        items = extract_list_items("- Alpha\n- 暂无关联知识\n- Beta\n")

        self.assertEqual(items, ["Alpha", "Beta"])

    def test_validate_body_markdown_rejects_outer_headings(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not contain H1/H2"):
            validate_body_markdown("# Bad", "answer")

    def test_validate_body_markdown_rejects_unclosed_fenced_code_block(self) -> None:
        with self.assertRaisesRegex(ValueError, "unclosed fenced code block"):
            validate_body_markdown("Run:\n```bash\necho hello", "answer")

    def test_body_markdown_allows_horizontal_rules_and_yaml_examples(self) -> None:
        body = "---\nkey: value\n---\n\nBody"

        self.assertEqual(validate_body_markdown(body, "answer"), body)
        self.assertEqual(normalize_embedded_body_markdown(body, "answer"), body)

    def test_normalize_embedded_body_markdown_demotes_outer_headings(self) -> None:
        self.assertEqual(
            normalize_embedded_body_markdown("# Title\n\n## Section\n\nBody", "answer"),
            "### Title\n\n### Section\n\nBody",
        )


if __name__ == "__main__":
    unittest.main()
