from __future__ import annotations

import io
import logging
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from knoarbor.runtime import configure_runtime_logging, runtime_logger, vault_write_lock


class RuntimeInfrastructureTests(unittest.TestCase):
    def test_runtime_logging_writes_to_knoarbor_log_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            log_path = configure_runtime_logging(vault)
            runtime_logger("unit").info("unit log message")
            for handler in logging.getLogger("knoarbor").handlers:
                handler.flush()
            self.assertEqual(log_path, (vault / ".knoarbor" / "logs" / "knoarbor.log").resolve())
            self.assertIn("unit log message", log_path.read_text(encoding="utf-8"))

    def test_runtime_logging_uses_one_active_runtime_handler(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_log = configure_runtime_logging(Path(first_dir))
            second_log = configure_runtime_logging(Path(second_dir))
            runtime_logger("unit").info("second vault only")
            for handler in logging.getLogger("knoarbor").handlers:
                handler.flush()
            self.assertNotIn("second vault only", first_log.read_text(encoding="utf-8"))
            self.assertIn("second vault only", second_log.read_text(encoding="utf-8"))

    def test_runtime_logging_can_emit_to_console_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stream = io.StringIO()
            with redirect_stderr(stream):
                configure_runtime_logging(Path(tmp_dir), console=True)
                configure_runtime_logging(Path(tmp_dir), console=True)
                runtime_logger("unit").info("console log message")
                for handler in logging.getLogger("knoarbor").handlers:
                    handler.flush()
            console_handlers = [
                handler for handler in logging.getLogger("knoarbor").handlers if getattr(handler, "_knoarbor_runtime_console", False)
            ]
            self.assertEqual(len(console_handlers), 1)
            self.assertIn("console log message", stream.getvalue())

    def test_vault_write_lock_is_reentrant_in_one_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            with vault_write_lock(vault):
                with vault_write_lock(vault):
                    (vault / "locked.txt").write_text("ok", encoding="utf-8")
            self.assertTrue((vault / ".knoarbor" / "locks" / "vault.write.lock").exists())


if __name__ == "__main__":
    unittest.main()
