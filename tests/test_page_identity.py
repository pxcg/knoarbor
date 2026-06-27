import unittest

from pydantic import ValidationError

from knoarbor.core.schemas import PageIdentity, normalize_identity_path


class PageIdentityTests(unittest.TestCase):
    def test_normalizes_paths_and_ids(self) -> None:
        identity = PageIdentity(
            canonical_path="/pages/Agent-Loop",
            title=" Agent Loop ",
            subject_kind="Architecture Pattern",
            atom_ids=[" atom-1 ", "atom-1", ""],
            relation_ids=[" rel-1 "],
            source_digest_ids=[" source-1 "],
        )

        self.assertEqual(identity.canonical_path, "pages/Agent-Loop.md")
        self.assertEqual(identity.title, "Agent Loop")
        self.assertEqual(identity.subject_kind, "architecture_pattern")
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

    def test_source_digest_role_is_inferred_from_path(self) -> None:
        identity = PageIdentity(
            canonical_path="sources/Agent-Loop-Source",
            title="Agent Loop Source",
        )

        self.assertEqual(identity.canonical_path, "sources/Agent-Loop-Source.md")
        self.assertEqual(identity.role, "source_digest")


if __name__ == "__main__":
    unittest.main()
