from __future__ import annotations

from pathlib import Path


RAW_ROOT_DIR = "raw"
RAW_INBOX_DIR = "inbox"
RAW_NORMALIZED_DIR = "normalized"
RAW_ASSETS_DIR = "assets"
RAW_SIDECARS_DIR = "sidecars"
WIKI_ROOT_DIR = "wiki"
WIKI_PAGES_DIR = "pages"
WIKI_SOURCES_DIR = "sources"
MAINTENANCE_ROOT_DIR = "maintenance"
RUNTIME_ROOT_DIR = ".knoarbor"


def vault_root(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve()


def raw_root(vault_path: Path) -> Path:
    return vault_root(vault_path) / RAW_ROOT_DIR


def raw_inbox_root(vault_path: Path) -> Path:
    return raw_root(vault_path) / RAW_INBOX_DIR


def raw_normalized_root(vault_path: Path) -> Path:
    return raw_root(vault_path) / RAW_NORMALIZED_DIR


def raw_assets_root(vault_path: Path) -> Path:
    return raw_root(vault_path) / RAW_ASSETS_DIR


def raw_sidecars_root(vault_path: Path) -> Path:
    return raw_root(vault_path) / RAW_SIDECARS_DIR


def raw_inbox_documents_root(vault_path: Path) -> Path:
    return raw_inbox_root(vault_path) / "documents"


def raw_inbox_notes_root(vault_path: Path) -> Path:
    return raw_inbox_root(vault_path) / "notes"


def raw_inbox_media_root(vault_path: Path) -> Path:
    return raw_inbox_root(vault_path) / "media"


def raw_normalized_markdown_root(vault_path: Path) -> Path:
    return raw_normalized_root(vault_path) / "markdown"


def raw_normalized_chats_root(vault_path: Path) -> Path:
    return raw_normalized_root(vault_path) / "chats"


def raw_normalized_excerpts_root(vault_path: Path) -> Path:
    return raw_normalized_root(vault_path) / "excerpts"


def raw_asset_images_root(vault_path: Path) -> Path:
    return raw_assets_root(vault_path) / "images"


def wiki_root(vault_path: Path) -> Path:
    return vault_root(vault_path) / WIKI_ROOT_DIR


def wiki_pages_root(vault_path: Path) -> Path:
    return wiki_root(vault_path) / WIKI_PAGES_DIR


def wiki_sources_root(vault_path: Path) -> Path:
    return wiki_root(vault_path) / WIKI_SOURCES_DIR


def maintenance_root(vault_path: Path) -> Path:
    return vault_root(vault_path) / MAINTENANCE_ROOT_DIR


def maintenance_reports_root(vault_path: Path) -> Path:
    return maintenance_root(vault_path) / "reports"


def maintenance_report_dir(vault_path: Path, report_kind: str) -> Path:
    return maintenance_reports_root(vault_path) / _safe_name(report_kind or "custom")


def maintenance_archives_root(vault_path: Path) -> Path:
    return maintenance_root(vault_path) / "archives"


def runtime_root(vault_path: Path) -> Path:
    return vault_root(vault_path) / RUNTIME_ROOT_DIR


def runtime_index_root(vault_path: Path) -> Path:
    return runtime_root(vault_path) / "index"


def runtime_ledger_path(vault_path: Path, ledger_name: str) -> Path:
    return runtime_root(vault_path) / "ledgers" / f"{_safe_name(ledger_name)}.jsonl"


def runtime_checkpoint_path(vault_path: Path, checkpoint_name: str) -> Path:
    return runtime_root(vault_path) / "checkpoints" / checkpoint_name


def runtime_relative_path(*parts: str) -> str:
    return str(Path(RUNTIME_ROOT_DIR, *parts).as_posix())


def ledger_relative_path(ledger_name: str) -> str:
    return runtime_relative_path("ledgers", f"{_safe_name(ledger_name)}.jsonl")


def checkpoint_relative_path(checkpoint_name: str) -> str:
    return runtime_relative_path("checkpoints", checkpoint_name)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip().lower()).strip("_") or "custom"
