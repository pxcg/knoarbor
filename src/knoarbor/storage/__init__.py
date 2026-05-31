"""Storage adapters for vault files, state, ledgers, and object stores."""
from knoarbor.storage.vault import VaultPage, VaultStore
from knoarbor.storage.ledger import append_jsonl_ledger, append_operation_ledger
from knoarbor.storage.wiki_index import (
    append_ingest_log,
    append_operation_log,
    ensure_machine_index,
    index_entry,
    is_machine_index_stale,
    machine_index_dir,
    page_record,
    relative_wiki_path,
    update_machine_index,
    update_index,
    wiki_link_for_path,
)
from knoarbor.storage.wiki_paths import (
    available_title_path,
    normalize_page_title,
    normalize_source_digest_title,
    normalize_wiki_page_path,
    resolve_existing_by_hash,
    resolve_existing_target,
    resolve_required_target,
    resolve_wiki_page,
    slugify_title,
)

__all__ = [
    "VaultPage",
    "VaultStore",
    "append_ingest_log",
    "append_jsonl_ledger",
    "append_operation_log",
    "append_operation_ledger",
    "available_title_path",
    "ensure_machine_index",
    "index_entry",
    "is_machine_index_stale",
    "machine_index_dir",
    "normalize_page_title",
    "normalize_source_digest_title",
    "normalize_wiki_page_path",
    "page_record",
    "relative_wiki_path",
    "resolve_existing_by_hash",
    "resolve_existing_target",
    "resolve_required_target",
    "resolve_wiki_page",
    "slugify_title",
    "update_machine_index",
    "update_index",
    "wiki_link_for_path",
]
