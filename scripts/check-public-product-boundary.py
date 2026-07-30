from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNED_ROOTS = (
    ROOT / ".github",
    ROOT / "desktop",
    ROOT / "renderer",
    ROOT / "src",
)
SCANNED_FILES = (
    ROOT / "pyproject.toml",
)
IGNORED_PARTS = {
    "dist",
    "node_modules",
    "package-lock.json",
    "release",
}
FORBIDDEN = (
    "SIEARBOR_",
    "SieArbor",
    "com.siemens.siearbor",
)


def main() -> int:
    violations: list[str] = []
    files = list(SCANNED_FILES)
    for root in SCANNED_ROOTS:
        files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(files):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN:
            if marker in content:
                violations.append(f"{relative}: private product marker {marker!r}")
    if violations:
        print("\n".join(violations))
        return 1
    print("Public product boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
