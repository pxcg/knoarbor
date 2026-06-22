import unittest

from pydantic import ValidationError

from knoarbor.core.schemas import (
    PageFacet,
    PageIdentity,
    normalize_facet,
    normalize_identity_path,
)


class PageIdentityTests(unittest.TestCase):
    def test_normalizes_paths_facets_and_ids(self) -> None:
        identity = PageIdentity(
            canonical_path="/pages/Agent-Loop",
            legacy_paths=[
                "concepts/Agent-Loop",
                "concepts/Agent-Loop.md",
                "pages/Agent-Loop.md",
            ],
            title=" Agent Loop ",
            subject_kind="Architecture Pattern",
            facets=["Concept", "workflow-pattern", "workflow pattern", ""],
            atom_ids=[" atom-1 ", "atom-1", ""],
            relation_ids=[" rel-1 "],
            source_digest_ids=[" source-1 "],
        )

        self.assertEqual(identity.canonical_path, "pages/Agent-Loop.md")
        self.assertEqual(identity.legacy_paths, ["concepts/Agent-Loop.md"])
        self.assertEqual(identity.title, "Agent Loop")
        self.assertEqual(identity.subject_kind, "architecture_pattern")
        self.assertEqual(identity.facets, ["concept", "workflow_pattern"])
        self.assertEqual(identity.atom_ids, ["atom-1"])
        self.assertEqual(identity.relation_ids, ["rel-1"])
        self.assertEqual(identity.source_digest_ids, ["source-1"])

    def test_rejects_invalid_paths(self) -> None:
        with self.assertRaises(ValueError):
            normalize_identity_path("")
        with self.assertRaises(ValueError):
            normalize_identity_path("../x")
        with self.assertRaises(ValueError):
            normalize_identity_path("pages/../x")
        with self.assertRaises(ValidationError):
            PageIdentity(canonical_path="../x", title="Bad")

    def test_source_digest_role_and_kind_are_consistent(self) -> None:
        identity = PageIdentity(
            canonical_path="sources/Agent-Loop-Source",
            title="Agent Loop Source",
            page_kind="source_digest",
        )

        self.assertEqual(identity.canonical_path, "sources/Agent-Loop-Source.md")
        self.assertEqual(identity.role, "source_digest")

        with self.assertRaises(ValidationError):
            PageIdentity(
                canonical_path="pages/Agent-Loop",
                title="Agent Loop",
                page_kind="concept",
                role="source_digest",
            )

    def test_generated_view_role_sets_kind(self) -> None:
        identity = PageIdentity(
            canonical_path="_views/Concepts",
            title="Concepts",
            role="generated_view",
        )

        self.assertEqual(identity.page_kind, "generated_view")

    def test_facet_alias_is_exported(self) -> None:
        facet: PageFacet = normalize_facet("Agent Engineering")

        self.assertEqual(facet, "agent_engineering")


if __name__ == "__main__":
    unittest.main()
