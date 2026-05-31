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
    update_frontmatter_value,
    validate_body_markdown,
)


class CoreMarkdownTests(unittest.TestCase):
    def test_parse_and_update_frontmatter(self) -> None:
        content = "---\ntype: concept\nstatus: draft\n---\n# Page\n"
        updated = update_frontmatter_value(content, "status", "reviewed")

        self.assertEqual(parse_frontmatter(updated)["status"], "reviewed")

    def test_replace_and_append_section(self) -> None:
        content = "# Page\n\n## Summary\n\nOld.\n"
        replaced = replace_section(content, "Summary", "New.")
        appended = append_to_section(replaced, "Notes", "First note.")

        self.assertEqual(extract_section(replaced, "Summary"), "New.")
        self.assertEqual(extract_section(appended, "Notes"), "First note.")

    def test_empty_section_does_not_capture_next_heading(self) -> None:
        content = "# Page\n\n## Evidence\n\n\n## Related Pages\n\n- [[concepts/Agent]]\n"
        replaced = replace_section(content, "Evidence", "- raw/notes/source.md")

        self.assertEqual(extract_section(content, "Evidence"), "")
        self.assertEqual(extract_section(content, "Related Pages"), "- [[concepts/Agent]]")
        self.assertIn("## Evidence\n\n- raw/notes/source.md\n## Related Pages", replaced)

    def test_extract_list_items_ignores_empty_placeholders(self) -> None:
        items = extract_list_items("- Alpha\n- 暂无关联知识\n- Beta\n")

        self.assertEqual(items, ["Alpha", "Beta"])

    def test_validate_body_markdown_rejects_outer_headings(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not contain H1/H2"):
            validate_body_markdown("# Bad", "answer")

    def test_normalize_embedded_body_markdown_demotes_outer_headings(self) -> None:
        self.assertEqual(
            normalize_embedded_body_markdown("# Title\n\n## Section\n\nBody", "answer"),
            "### Title\n\n### Section\n\nBody",
        )


if __name__ == "__main__":
    unittest.main()
