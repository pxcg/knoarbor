from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path


class KnoArborIgnore:
    """Gitignore-style matcher for source discovery paths."""

    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns

    @classmethod
    def from_file(cls, path: Path) -> KnoArborIgnore:
        if not path.exists():
            return cls([])
        patterns: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            patterns.append(text)
        return cls(patterns)

    def ignored(self, path: str | Path) -> bool:
        normalized = str(path).replace("\\", "/").lstrip("./")
        ignored = False
        for pattern in self.patterns:
            negated = pattern.startswith("!")
            raw_pattern = pattern[1:] if negated else pattern
            if _matches(normalized, raw_pattern):
                ignored = not negated
        return ignored


def _matches(path: str, pattern: str) -> bool:
    normalized_pattern = pattern.replace("\\", "/").lstrip("./")
    if normalized_pattern.endswith("/"):
        prefix = normalized_pattern.rstrip("/") + "/"
        return path == normalized_pattern.rstrip("/") or path.startswith(prefix)
    return fnmatch(path, normalized_pattern) or fnmatch(Path(path).name, normalized_pattern)
