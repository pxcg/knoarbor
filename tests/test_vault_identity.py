from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knoarbor.storage.vault_identity import ensure_vault_identity, vault_identity_path
from knoarbor.storage.wiki_init import init_wiki_vault


class VaultIdentityTests(unittest.TestCase):
    def test_init_creates_a_stable_vault_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vault"
            init_wiki_vault(vault)
            first = ensure_vault_identity(vault)
            second = ensure_vault_identity(vault)

            self.assertTrue(vault_identity_path(vault).exists())
            self.assertEqual(first, second)
            self.assertTrue(first.startswith("vault:"))
