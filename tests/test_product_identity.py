from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from knoarbor.product import PRODUCT, _validate_manifest, product_env, product_env_name


ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "src" / "knoarbor" / "product_manifest.json"


class ProductIdentityTests(unittest.TestCase):
    def test_public_identity_is_loaded_from_manifest(self) -> None:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(PRODUCT.name, payload["product"]["name"])
        self.assertEqual(PRODUCT.service_title, payload["product"]["service_title"])
        self.assertEqual(PRODUCT.default_vault_name, payload["product"]["default_vault_name"])
        self.assertEqual(PRODUCT.env_prefix, payload["environment"]["prefix"])
        self.assertEqual(PRODUCT.desktop_app_id, payload["desktop"]["app_id"])

    def test_manifest_rejects_unknown_fields(self) -> None:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        invalid = deepcopy(payload)
        invalid["private_override"] = {}

        with self.assertRaisesRegex(ValueError, "fields must be"):
            _validate_manifest(invalid)

    def test_manifest_rejects_wrong_capability_type(self) -> None:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        invalid = deepcopy(payload)
        invalid["capabilities"]["desktop_updates"] = "false"

        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            _validate_manifest(invalid)

    def test_product_environment_uses_one_validated_prefix(self) -> None:
        self.assertEqual(product_env_name("config_path"), "KNOARBOR_CONFIG_PATH")
        with patch.dict(os.environ, {"KNOARBOR_CONFIG_PATH": " /tmp/config.yaml "}):
            self.assertEqual(product_env("config_path"), "/tmp/config.yaml")
        with self.assertRaisesRegex(ValueError, "Invalid product environment suffix"):
            product_env("../config")

    def test_generated_typescript_adapters_are_current(self) -> None:
        result = subprocess.run(
            ["python3", "scripts/generate-product-identity.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_packaging_identity_matches_manifest(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        desktop_builder = (ROOT / "desktop" / "electron-builder.config.cjs").read_text(encoding="utf-8")
        renderer_manifest = json.loads((ROOT / "renderer" / "public" / "site.webmanifest").read_text(encoding="utf-8"))

        self.assertIn(f'appId: "{manifest["desktop"]["app_id"]}"', desktop_builder)
        self.assertIn(f'productName: "{manifest["product"]["name"]}"', desktop_builder)
        self.assertEqual(renderer_manifest["name"], manifest["product"]["name"])


if __name__ == "__main__":
    unittest.main()
