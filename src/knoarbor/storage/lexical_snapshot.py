from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Callable, Iterator, Literal

from knoarbor.retrieval.query_text import LexicalQueryPlan, TechnicalAnchor, build_lexical_query_plan, lexical_tokens
LEXICAL_SNAPSHOT_SCHEMA = "lexical_snapshot.v7"


@dataclass(frozen=True)
class LexicalMatch:
    doc_id: str
    channel: Literal["atom_claim", "raw_lexical"]
    rank: int
    score: float
    metadata: dict[str, Any]
    matched_terms: list[str]


@dataclass(frozen=True)
class LexicalSearchResult:
    matches: tuple[LexicalMatch, ...]
    fts_hit_count: int
    ineligible_hit_count: int


@dataclass(frozen=True)
class RetrievalSafety:
    deadline: float | None = None
    max_accumulated_bytes: int | None = None
    max_materialized_bytes: int | None = None
    raise_if_cancelled: Callable[[], None] | None = None

    @classmethod
    def with_timeout(
        cls,
        seconds: float | None = 10.0,
        *,
        max_accumulated_bytes: int | None = 64 * 1024 * 1024,
        max_materialized_bytes: int | None = 64 * 1024 * 1024,
        raise_if_cancelled: Callable[[], None] | None = None,
    ) -> "RetrievalSafety":
        return cls(
            deadline=time.monotonic() + seconds if seconds is not None else None,
            max_accumulated_bytes=max_accumulated_bytes,
            max_materialized_bytes=max_materialized_bytes,
            raise_if_cancelled=raise_if_cancelled,
        )


class RetrievalSafetyExceeded(RuntimeError):
    def __init__(
        self,
        *,
        continuation_offset: int,
        continuation_rank: int,
        reason: str,
        partial_matches: tuple[LexicalMatch, ...] = (),
    ) -> None:
        super().__init__(reason)
        self.continuation_offset = continuation_offset
        self.continuation_rank = continuation_rank
        self.reason = reason
        self.partial_matches = partial_matches


def build_lexical_snapshot(
    vault_path: Path,
    target: Path,
    *,
    fact_generation: str,
    atom_records: list[Any],
    raw_records: list[Any],
) -> dict[str, object]:
    """Build one deterministic FTS5 snapshot from active factual records."""

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    connection = sqlite3.connect(target)
    try:
        _require_fts5(connection)
        connection.executescript(
            """
            pragma journal_mode=DELETE;
            pragma synchronous=FULL;
            create table retrieval_metadata (
              key text primary key,
              value text not null
            );
            create table retrieval_documents (
              doc_id text primary key,
              channel text not null,
              revision_id text not null,
              source_record_id text not null,
              local_id text not null,
              raw_revision_id text not null,
              source_unit_id text not null,
              evidence_id text not null,
              metadata_json text not null
            );
            create index retrieval_documents_batch on retrieval_documents(channel, revision_id, source_record_id);
            create index retrieval_documents_raw on retrieval_documents(raw_revision_id, source_unit_id);
            create index retrieval_documents_evidence on retrieval_documents(evidence_id);
            create table retrieval_raw_units (
              evidence_id text primary key,
              rerank_text text not null
            );
            create virtual table retrieval_fts using fts5(
              doc_id unindexed,
              channel unindexed,
              text,
              aliases,
              entities,
              predicate,
              payload,
              title,
              structure,
              source,
              content,
              tokenize='unicode61'
            );
            """
        )
        documents = [*_atom_documents(atom_records), *_raw_documents(vault_path, raw_records)]
        documents.sort(key=lambda item: str(item["doc_id"]))
        raw_units: dict[str, str] = {}
        for document in documents:
            metadata = document.pop("metadata")
            rerank_text = str(document.pop("rerank_text", "") or "")
            evidence_id = str(metadata.get("evidence_id") or "")
            if document["channel"] == "raw_lexical" and evidence_id:
                existing_text = raw_units.setdefault(
                    evidence_id,
                    rerank_text,
                )
                if existing_text != rerank_text:
                    raise RuntimeError(
                        "Raw lexical windows disagree on their parent unit."
                    )
            connection.execute(
                """
                insert into retrieval_documents(
                  doc_id, channel, revision_id, source_record_id, local_id,
                  raw_revision_id, source_unit_id, evidence_id, metadata_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document["doc_id"], document["channel"],
                    str(metadata.get("revision_id") or ""),
                    str(metadata.get("source_record_id") or ""),
                    str(metadata.get("atom_id") or metadata.get("window_index") or ""),
                    str(metadata.get("raw_revision_id") or ""),
                    str(metadata.get("source_unit_id") or ""),
                    str(metadata.get("evidence_id") or ""),
                    _canonical_json(metadata),
                ),
            )
            connection.execute(
                """
                insert into retrieval_fts(
                  doc_id, channel, text, aliases, entities, predicate, payload,
                  title, structure, source, content
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(document[name] for name in (
                    "doc_id", "channel", "text", "aliases", "entities",
                    "predicate", "payload", "title", "structure", "source", "content",
                )),
            )
        connection.executemany(
            """
            insert into retrieval_raw_units(evidence_id, rerank_text)
            values (?, ?)
            """,
            sorted(raw_units.items()),
        )
        metadata = {
            "schema_version": LEXICAL_SNAPSHOT_SCHEMA,
            "fact_generation": fact_generation,
            "document_count": len(documents),
            "atom_document_count": sum(item["channel"] == "atom_claim" for item in documents),
            "raw_window_count": sum(item["channel"] == "raw_lexical" for item in documents),
            "raw_unit_count": len(raw_units),
        }
        connection.executemany(
            "insert into retrieval_metadata(key, value) values (?, ?)",
            [(key, _canonical_json(value)) for key, value in sorted(metadata.items())],
        )
        connection.commit()
        connection.execute("vacuum")
    finally:
        connection.close()
    verify_lexical_snapshot(target, expected_fact_generation=fact_generation)
    return metadata


def verify_lexical_snapshot(
    path: Path,
    *,
    expected_fact_generation: str | None = None,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError("Lexical retrieval snapshot is missing.")
    if raise_if_cancelled is not None:
        raise_if_cancelled()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        _require_fts5(connection)
        quick = connection.execute("pragma quick_check").fetchone()
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        if quick is None or quick[0] != "ok":
            raise RuntimeError("Lexical retrieval snapshot failed SQLite integrity verification.")
        rows = connection.execute("select key, value from retrieval_metadata order by key").fetchall()
        metadata = {str(key): json.loads(str(value)) for key, value in rows}
        if metadata.get("schema_version") != LEXICAL_SNAPSHOT_SCHEMA:
            raise RuntimeError("Lexical retrieval snapshot schema is unsupported.")
        if expected_fact_generation is not None and metadata.get("fact_generation") != expected_fact_generation:
            raise RuntimeError("Lexical retrieval snapshot fact generation is stale.")
        raw_unit_count = connection.execute(
            "select count(*) from retrieval_raw_units"
        ).fetchone()
        if (
            raw_unit_count is None
            or int(raw_unit_count[0]) != int(metadata.get("raw_unit_count") or 0)
        ):
            raise RuntimeError(
                "Lexical retrieval Raw-unit metadata is incomplete."
            )
        connection.execute("select rowid from retrieval_fts where retrieval_fts match 'fts5' limit 1").fetchall()
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        return metadata
    except sqlite3.Error as exc:
        raise RuntimeError("Lexical retrieval snapshot is invalid or FTS5 is unavailable.") from exc
    finally:
        connection.close()


def search_lexical_snapshot(
    path: Path,
    query: str,
    *,
    channel: Literal["atom_claim", "raw_lexical"],
    safety: RetrievalSafety,
    offset: int = 0,
    rank_offset: int = 0,
    source_record_ids: frozenset[str] | None = None,
    source_unit_ids: frozenset[str] | None = None,
) -> LexicalSearchResult:
    plan = build_lexical_query_plan(query)
    terms = list(plan.terms)
    if not terms:
        return LexicalSearchResult(matches=(), fts_hit_count=0, ineligible_hit_count=0)
    expression = _fts_expression(plan)
    weights = (0.0, 0.0, 4.0, 3.0, 2.0, 1.5, 0.5, 3.0, 2.0, 0.5, 1.0)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        scope_clauses: list[str] = []
        scope_parameters: list[str] = []
        if source_record_ids is not None:
            if not source_record_ids:
                return LexicalSearchResult(
                    matches=(),
                    fts_hit_count=0,
                    ineligible_hit_count=0,
                )
            placeholders = ",".join("?" for _ in source_record_ids)
            scope_clauses.append(
                f"d.source_record_id in ({placeholders})"
            )
            scope_parameters.extend(sorted(source_record_ids))
        if source_unit_ids is not None and channel == "raw_lexical":
            if not source_unit_ids:
                return LexicalSearchResult(
                    matches=(),
                    fts_hit_count=0,
                    ineligible_hit_count=0,
                )
            placeholders = ",".join("?" for _ in source_unit_ids)
            scope_clauses.append(f"d.source_unit_id in ({placeholders})")
            scope_parameters.extend(sorted(source_unit_ids))
        scope_sql = (
            " and " + " and ".join(scope_clauses)
            if scope_clauses
            else ""
        )
        cursor = connection.execute(
            f"""
            select f.doc_id, f.channel, f.text, f.aliases, f.entities,
                   f.predicate, f.payload, f.title, f.structure, f.source, f.content,
                   d.metadata_json, u.rerank_text,
                   bm25(retrieval_fts, {','.join(str(value) for value in weights)}) as lexical_score
              from retrieval_fts f
              join retrieval_documents d on d.doc_id = f.doc_id
              left join retrieval_raw_units u
                on u.evidence_id = d.evidence_id
             where retrieval_fts match ? and f.channel = ?{scope_sql}
             order by lexical_score asc, f.doc_id asc
             limit -1 offset ?
            """,
            (expression, channel, *scope_parameters, offset),
        )
        output: list[LexicalMatch] = []
        accumulated_bytes = 0
        materialized_bytes = 0
        fts_hit_count = 0
        ineligible_hit_count = 0
        for row in cursor:
            if safety.raise_if_cancelled is not None:
                safety.raise_if_cancelled()
            metadata_json = str(row["metadata_json"])
            metadata = json.loads(metadata_json)
            if channel == "raw_lexical":
                metadata["rerank_text"] = str(
                    row["rerank_text"] or ""
                )
            if (
                channel == "atom_claim"
                and source_unit_ids is not None
                and not _atom_intersects_source_unit_scope(
                    metadata,
                    source_unit_ids,
                )
            ):
                continue
            fts_hit_count += 1
            if safety.deadline is not None and time.monotonic() > safety.deadline:
                raise RetrievalSafetyExceeded(
                    continuation_offset=offset + fts_hit_count - 1,
                    continuation_rank=rank_offset + len(output),
                    reason="deadline",
                    partial_matches=tuple(output),
                )
            accumulated_bytes += len(metadata_json.encode("utf-8"))
            if safety.max_accumulated_bytes is not None and accumulated_bytes > safety.max_accumulated_bytes:
                raise RetrievalSafetyExceeded(
                    continuation_offset=offset + fts_hit_count - 1,
                    continuation_rank=rank_offset + len(output),
                    reason="accumulated_bytes",
                    partial_matches=tuple(output),
                )
            document_tokens = {
                token
                for field in ("text", "aliases", "entities", "predicate", "payload", "title", "structure", "content")
                for token in str(row[field] or "").split()
            }
            source_tokens = set(str(row["source"] or "").split())
            match = LexicalMatch(
                doc_id=str(row["doc_id"]),
                channel=channel,
                rank=rank_offset + len(output) + 1,
                score=-float(row["lexical_score"]),
                metadata=metadata,
                matched_terms=[term for term in terms if term in document_tokens or term in source_tokens],
            )
            retained_bytes = _deep_size(match)
            if (
                safety.max_materialized_bytes is not None
                and materialized_bytes + retained_bytes > safety.max_materialized_bytes
            ):
                raise RetrievalSafetyExceeded(
                    continuation_offset=offset + fts_hit_count - 1,
                    continuation_rank=rank_offset + len(output),
                    reason="materialized_bytes",
                    partial_matches=tuple(output),
                )
            materialized_bytes += retained_bytes
            output.append(match)
        return LexicalSearchResult(
            matches=tuple(output),
            fts_hit_count=fts_hit_count,
            ineligible_hit_count=ineligible_hit_count,
        )
    except sqlite3.Error as exc:
        raise RuntimeError("Lexical retrieval snapshot query failed.") from exc
    finally:
        connection.close()


def read_atom_batch_documents(path: Path, *, revision_id: str, source_record_id: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            select metadata_json from retrieval_documents
             where channel='atom_claim' and revision_id=? and source_record_id=?
             order by local_id, doc_id
            """,
            (revision_id, source_record_id),
        ).fetchall()
        return [json.loads(str(row[0])) for row in rows]
    except sqlite3.Error as exc:
        raise RuntimeError("Lexical retrieval atom batch lookup failed.") from exc
    finally:
        connection.close()


def read_raw_locator_metadata_by_evidence_ids(path: Path, evidence_ids: list[str]) -> list[dict[str, Any]]:
    if not evidence_ids:
        return []
    placeholders = ",".join("?" for _ in evidence_ids)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            f"""
            select d.metadata_json, u.rerank_text
              from retrieval_documents d
              join retrieval_raw_units u
                on u.evidence_id = d.evidence_id
             where d.channel='raw_lexical'
               and d.evidence_id in ({placeholders})
             order by d.evidence_id, d.local_id, d.doc_id
            """,
            tuple(evidence_ids),
        ).fetchall()
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            metadata = json.loads(str(row[0]))
            metadata["rerank_text"] = str(row[1] or "")
            evidence_id = str(metadata.get("evidence_id") or "")
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            output.append(metadata)
        return output
    except sqlite3.Error as exc:
        raise RuntimeError("Lexical retrieval evidence-handle locator lookup failed.") from exc
    finally:
        connection.close()


def _atom_documents(records: list[Any]) -> Iterator[dict[str, Any]]:
    for atom in records:
        if atom.atom_type == "synthesis":
            continue
        identity = _atom_identity(atom)
        payload = atom.payload
        aliases = _strings(payload.get("aliases"))
        entities = [
            *_strings(payload.get("entity_names")),
            *_strings(payload.get("entity_ids")),
            *_object_strings(payload.get("subject")),
            *_object_strings(payload.get("object")),
        ]
        yield {
            "doc_id": identity,
            "channel": "atom_claim",
            "text": _token_text(atom.text),
            "aliases": _token_text(" ".join(aliases)),
            "entities": _token_text(" ".join(entities)),
            "predicate": _token_text(str(payload.get("predicate") or "")),
            "payload": _token_text(_payload_text(payload)),
            "title": "",
            "structure": "",
            "source": "",
            "content": "",
            "metadata": _compact_atom_metadata(atom),
        }


def _atom_intersects_source_unit_scope(
    metadata: dict[str, Any],
    source_unit_ids: frozenset[str],
) -> bool:
    atom_source_units = {
        str(value)
        for value in (
            metadata.get("source_unit_ids")
            or [metadata.get("source_unit_id")]
        )
        if value
    }
    return bool(atom_source_units.intersection(source_unit_ids))


def _raw_documents(vault_path: Path, records: list[Any]) -> Iterator[dict[str, Any]]:
    if not records:
        return
    vault_id = _vault_identity(vault_path)
    for raw in records:
        evidence_id = f"evh:{_stable_hash(vault_id, raw.raw_revision_id, raw.source_unit_id)}"
        source_identity = Path(str(raw.source_path or "")).stem
        for window_index, start, end, content in _locator_windows(raw.content or raw.excerpt):
            doc_id = f"raw:{_stable_hash(raw.raw_revision_id, raw.source_unit_id, str(window_index), content)}"
            metadata = {
                "evidence_id": evidence_id,
                "raw_record_id": raw.raw_record_id,
                "raw_revision_id": raw.raw_revision_id,
                "revision_id": raw.revision_id,
                "source_unit_id": raw.source_unit_id,
                "source_record_id": raw.source_record_id,
                "processing_record_id": raw.processing_record_id,
                "source_path": raw.source_path,
                "title": raw.title,
                "char_start": raw.char_start,
                "char_end": raw.char_end,
                "locator_page_paths": list(raw.locator_page_paths),
                "window_index": window_index,
                "window_char_start": start,
                "window_char_end": end,
            }
            yield {
                "doc_id": doc_id,
                "channel": "raw_lexical",
                "text": "",
                "aliases": "",
                "entities": "",
                "predicate": "",
                "payload": "",
                "title": _token_text(raw.title),
                "structure": _token_text(" ".join(raw.structural_path)),
                "source": _token_text(source_identity),
                "content": _token_text(content),
                "metadata": metadata,
                "rerank_text": raw.content or raw.excerpt,
            }


def _compact_atom_metadata(atom: Any) -> dict[str, Any]:
    """Keep only retrieval-required atom evidence in the rebuildable index."""

    metadata = atom.model_dump(mode="json")
    payload = dict(metadata.get("payload") or {})
    for key in ("subject", "object"):
        value = payload.get(key)
        if isinstance(value, dict) and "evidence" in value:
            payload[key] = {
                nested_key: nested_value
                for nested_key, nested_value in value.items()
                if nested_key != "evidence"
            }
    metadata["payload"] = payload
    if metadata.get("atom_type") != "claim":
        metadata["evidence"] = []
        return metadata
    metadata["evidence"] = [
        _compact_claim_evidence(item)
        for item in metadata.get("evidence", [])
        if isinstance(item, dict)
    ]
    return metadata


def _compact_claim_evidence(item: dict[str, Any]) -> dict[str, Any]:
    output = {
        key: item[key]
        for key in ("source_unit_id", "char_start", "char_end")
        if item.get(key) is not None
    }
    if not (
        isinstance(item.get("char_start"), int)
        and isinstance(item.get("char_end"), int)
        and item["char_start"] < item["char_end"]
    ):
        excerpt = str(item.get("excerpt") or "").strip()
        if excerpt:
            output["excerpt"] = excerpt
    return output


def _locator_windows(content: str, *, size: int = 256, overlap: int = 64) -> Iterator[tuple[int, int, int, str]]:
    spans = [(match.start(), match.end()) for match in re.finditer(r"[A-Za-z0-9][A-Za-z0-9_.+-]*|[\u3400-\u9fff]|[^\s]", content)]
    if not spans:
        return
    start_index = 0
    window_index = 0
    while start_index < len(spans):
        end_index = min(len(spans), start_index + size)
        start = spans[start_index][0]
        end = spans[end_index - 1][1]
        yield window_index, start, end, content[start:end]
        if end_index >= len(spans):
            break
        start_index = max(start_index + 1, end_index - overlap)
        window_index += 1


def _require_fts5(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("create virtual table if not exists temp.__fts5_probe using fts5(body)")
        connection.execute("drop table if exists temp.__fts5_probe")
    except sqlite3.Error as exc:
        raise RuntimeError("This runtime does not provide the required SQLite FTS5 capability.") from exc


def _atom_identity(atom: Any) -> str:
    return "atom:" + _stable_hash(atom.revision_id or atom.raw_revision_id or "", atom.source_record_id, atom.atom_id)


def _token_text(value: str) -> str:
    return " ".join(lexical_tokens(value))


def _fts_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _fts_expression(plan: LexicalQueryPlan) -> str:
    technical_terms = {
        variant
        for anchor in plan.technical_anchors
        for variant in (*anchor.variants, *anchor.parts)
    }
    ordinary_clauses = [
        _fts_quote(term)
        for term in plan.terms
        if term not in technical_terms
    ]
    technical_clauses = [
        _technical_fts_clause(anchor)
        for anchor in plan.technical_anchors
    ]
    required_clauses = [
        _technical_fts_clause(anchor)
        for anchor in plan.technical_anchors
        if any(character.isdigit() for variant in anchor.variants for character in variant)
    ]
    all_rank_terms = [*technical_clauses, *ordinary_clauses]
    if not required_clauses:
        return " OR ".join(all_rank_terms)
    required_identity = " AND ".join(required_clauses)
    optional_rank_terms = " OR ".join(
        all_rank_terms
    )
    return (
        f"({required_identity}) AND ({optional_rank_terms})"
        if optional_rank_terms
        else required_identity
    )


def _technical_fts_clause(anchor: TechnicalAnchor) -> str:
    compound_variants = [variant for variant in anchor.variants if variant not in anchor.parts]
    if len(anchor.parts) == 1:
        compound_variants.extend(anchor.parts)
    alternatives = [_fts_quote(variant) for variant in dict.fromkeys(compound_variants)]
    if len(anchor.parts) > 1:
        alternatives.append("(" + " AND ".join(_fts_quote(part) for part in anchor.parts) + ")")
    return "(" + " OR ".join(alternatives) + ")"


def _stable_hash(*values: str) -> str:
    return sha256("\x1f".join(values).encode("utf-8")).hexdigest()[:24]


def _vault_identity(vault_path: Path) -> str:
    path = vault_path.expanduser().resolve() / ".knoarbor" / "vault_identity.json"
    if not path.is_file():
        raise RuntimeError("Vault identity is missing while building lexical retrieval snapshot.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    identity = str(payload.get("identity") or "")
    if not identity:
        raise RuntimeError("Vault identity is invalid while building lexical retrieval snapshot.")
    return identity


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _deep_size(value: object, seen: set[int] | None = None) -> int:
    visited = seen if seen is not None else set()
    identity = id(value)
    if identity in visited:
        return 0
    visited.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        return size + sum(_deep_size(key, visited) + _deep_size(item, visited) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return size + sum(_deep_size(item, visited) for item in value)
    if isinstance(value, LexicalMatch):
        return size + sum(
            _deep_size(item, visited)
            for item in (value.doc_id, value.channel, value.rank, value.score, value.metadata, value.matched_terms)
        )
    return size


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _object_strings(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [text for text in [str(value.get("name") or "").strip(), *_strings(value.get("aliases"))] if text]


def _payload_text(payload: dict[str, Any]) -> str:
    values: list[str] = []
    for value in payload.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value if isinstance(item, (str, int, float)))
        elif isinstance(value, dict):
            values.extend(str(item) for item in value.values() if isinstance(item, (str, int, float)))
    return " ".join(values)
