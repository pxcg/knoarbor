from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.ignore import KnoArborIgnore
from knoarbor.storage.wiki_init import init_wiki_vault


class WikiInitTests(unittest.TestCase):
    def test_init_wiki_vault_creates_schema_index_log_and_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "wiki"

            result = init_wiki_vault(vault)

            self.assertTrue((vault / "SCHEMA.md").exists())
            self.assertTrue((vault / "index.md").exists())
            self.assertTrue((vault / "log.md").exists())
            self.assertTrue((vault / ".knoarborignore").exists())
            self.assertTrue((vault / "raw" / "documents" / "markdown").is_dir())
            self.assertIn("SCHEMA.md", result.created_paths)

    def test_knoarborignore_supports_negation_and_directory_patterns(self) -> None:
        matcher = KnoArborIgnore(["confidential/", "*.key", "!confidential/public.md"])

        self.assertTrue(matcher.ignored("confidential/private.md"))
        self.assertTrue(matcher.ignored("secret.key"))
        self.assertFalse(matcher.ignored("confidential/public.md"))


if __name__ == "__main__":
    unittest.main()
