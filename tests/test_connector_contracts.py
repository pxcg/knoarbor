from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.connectors.registry import ConnectorRegistry


class ConnectorContractTests(unittest.TestCase):
    def test_registry_exposes_capabilities(self) -> None:
        capabilities = ConnectorRegistry().capabilities()
        names = {item.name for item in capabilities}

        expected = {"markdown", "hermes", "codex", "openclaw", "claude_code", "generic_chat"}
        self.assertTrue(expected.issubset(names))
        markdown = next(item for item in capabilities if item.name == "markdown")
        self.assertEqual(markdown.source_types, ["markdown"])
        self.assertEqual(markdown.settings_schema["required"], ["roots"])

    def test_registered_connectors_have_stable_contract_metadata(self) -> None:
        capabilities = {item.name: item for item in ConnectorRegistry().capabilities()}

        expected_source_types = {
            "markdown": ["markdown"],
            "hermes": ["hermes_chat"],
            "codex": ["codex_chat"],
            "openclaw": ["openclaw_chat"],
            "claude_code": ["claude_code_chat"],
            "generic_chat": ["generic_chat"],
        }
        for name, source_types in expected_source_types.items():
            with self.subTest(name=name):
                capability = capabilities[name]
                self.assertEqual(capability.source_types, source_types)
                self.assertTrue(capability.settings_schema)
                self.assertTrue(capability.supports_discovery)
                self.assertTrue(capability.supports_checkpoint)
                self.assertEqual(
                    capability.supports_segmentation_hint,
                    name in {"hermes", "codex", "openclaw", "claude_code", "generic_chat"},
                )
                self.assertFalse(capability.requires_external_service)

    def test_registry_health_reports_disabled_without_discovery(self) -> None:
        health = ConnectorRegistry().health({"markdown": ConnectorConfig(enabled=False)})
        markdown = next(item for item in health if item.name == "markdown")

        self.assertTrue(markdown.ok)
        self.assertEqual(markdown.code, "disabled")

    def test_registry_health_reports_discovery_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing"
            health = ConnectorRegistry().health({"markdown": ConnectorConfig(enabled=True, settings={"roots": [str(missing)]})})

        markdown = next(item for item in health if item.name == "markdown")
        self.assertFalse(markdown.ok)
        self.assertEqual(markdown.code, "SourceNotFound")


if __name__ == "__main__":
    unittest.main()
