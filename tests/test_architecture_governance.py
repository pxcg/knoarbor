from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "check-architecture.py"
SPEC = importlib.util.spec_from_file_location("check_architecture", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECK_ARCHITECTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK_ARCHITECTURE)


class ArchitectureGovernanceTests(unittest.TestCase):
    def test_import_cycle_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "knoarbor"
            root.mkdir()
            (root / "__init__.py").write_text("", encoding="utf-8")
            (root / "first.py").write_text("from knoarbor import second\n", encoding="utf-8")
            (root / "second.py").write_text("from knoarbor import first\n", encoding="utf-8")

            errors = CHECK_ARCHITECTURE._check_import_cycles(root)

        self.assertEqual(len(errors), 1)
        self.assertIn("knoarbor.first", errors[0])
        self.assertIn("knoarbor.second", errors[0])

    def test_type_checking_import_does_not_create_runtime_cycle(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "knoarbor"
            root.mkdir()
            (root / "__init__.py").write_text("", encoding="utf-8")
            (root / "first.py").write_text(
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from knoarbor import second\n",
                encoding="utf-8",
            )
            (root / "second.py").write_text("from knoarbor import first\n", encoding="utf-8")

            errors = CHECK_ARCHITECTURE._check_import_cycles(root)

        self.assertEqual(errors, [])

    def test_storage_package_root_cannot_eagerly_reexport_owner_modules(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "knoarbor"
            storage = root / "storage"
            storage.mkdir(parents=True)
            (root / "__init__.py").write_text("", encoding="utf-8")
            (storage / "__init__.py").write_text(
                "from knoarbor.storage.wiki_index import load_index\n",
                encoding="utf-8",
            )
            (storage / "wiki_index.py").write_text(
                "def load_index():\n    return {}\n",
                encoding="utf-8",
            )

            errors = CHECK_ARCHITECTURE._check_backend_composition_surfaces(root)

        self.assertEqual(len(errors), 1)
        self.assertIn("storage package root must remain composition-free", errors[0])

    def test_chat_module_cannot_depend_on_application_container(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            services = Path(tmp_dir) / "services"
            services.mkdir()
            (services / "chat_messages.py").write_text(
                "def merge_messages(existing, latest):\n    return latest\n",
                encoding="utf-8",
            )
            (services / "chat_agent.py").write_text(
                "def run(services: ApplicationServices):\n    return services.chat\n",
                encoding="utf-8",
            )

            errors = CHECK_ARCHITECTURE._check_chat_boundaries(services)

        self.assertTrue(any("full application service container" in error for error in errors))

    def test_renderer_client_cannot_implement_domain_behavior(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            renderer = Path(tmp_dir) / "src"
            (renderer / "api").mkdir(parents=True)
            (renderer / "api" / "client.ts").write_text(
                "export async function getHealth() { return fetch('/health'); }\n",
                encoding="utf-8",
            )

            errors = CHECK_ARCHITECTURE._check_renderer_direction(renderer)

        self.assertTrue(any("API composition surface" in error for error in errors))

    def test_renderer_routes_must_project_page_capabilities(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            renderer = Path(tmp_dir) / "src"
            (renderer / "api" / "contracts").mkdir(parents=True)
            (renderer / "i18n" / "locales").mkdir(parents=True)
            (renderer / "appRoutes.tsx").write_text(
                "export const routes = <ChatPage context={context} />;\n",
                encoding="utf-8",
            )

            errors = CHECK_ARCHITECTURE._check_renderer_direction(renderer)

        self.assertTrue(any("full application context" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

