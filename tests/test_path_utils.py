from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.path_utils import file_uri_to_path_string


class PathUtilsTests(unittest.TestCase):
    def test_posix_file_uri(self) -> None:
        self.assertEqual(file_uri_to_path_string("file:///Users/alice/Notes/a%20b.md", platform="posix"), "/Users/alice/Notes/a b.md")

    def test_windows_drive_file_uri(self) -> None:
        self.assertEqual(
            file_uri_to_path_string("file:///C:/Users/Alice/Notes/a%20b.md", platform="nt"),
            r"C:\Users\Alice\Notes\a b.md",
        )

    def test_windows_localhost_file_uri(self) -> None:
        self.assertEqual(
            file_uri_to_path_string("file://localhost/C:/Users/Alice/Notes/a.md", platform="nt"),
            r"C:\Users\Alice\Notes\a.md",
        )

    def test_windows_unc_file_uri(self) -> None:
        self.assertEqual(
            file_uri_to_path_string("file://server/share/folder/a.md", platform="nt"),
            r"\\server\share\folder\a.md",
        )

    def test_rejects_non_file_uri(self) -> None:
        with self.assertRaisesRegex(ValueError, "Expected file:// URI"):
            file_uri_to_path_string("https://example.com/a.md")


if __name__ == "__main__":
    unittest.main()
