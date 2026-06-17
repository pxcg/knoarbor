#!/usr/bin/env python3
"""Run a lightweight local chunk-RAG baseline for KnoArbor chat fixtures.

The baseline is intentionally simple: raw files -> chunks -> BM25 retrieval ->
optional model answer. It is for comparing wiki-page answers with conventional
chunk retrieval without starting a database or external RAG product.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from knoarbor.core.config import default_config_path, load_config  # noqa: E402
from knoarbor.semantic.llm import ChatCompletionRequest, ChatMessage, ModelGateway  # noqa: E402


DEFAULT_FIXTURE = Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json")
DEFAULT_OUTPUT_ROOT = Path("tmp/rag-baselines")

AGENT_ARCHITECTURE_RAW_FILES = [
    Path("/Users/pxcg/Documents/Obsidian/Notes/02 AI Agent/Agent.md"),
    Path("/Users/pxcg/Documents/Obsidian/Notes/02 AI Agent/MCP.md"),
    Path("/Users/pxcg/Documents/Obsidian/Notes/02 AI Agent/OpenClaw架构.md"),
    Path("/Users/pxcg/.hermes/sessions/session_20260505_173432_47d596.json"),
    Path("/Users/pxcg/.codex/sessions/2026/05/26/rollout-2026-05-26T23-18-09-019e64dd-5f34-7020-bb79-01e35ed3ab51.jsonl"),
    Path("/Users/pxcg/.claude/projects/-Users-pxcg/6184bdcf-4789-4eea-9f5f-76b52330676a.jsonl"),
]


@dataclass(frozen=True)
class FixtureTurn:
    turn: int
    question: str
    expected_pages: list[str] = field(default_factory=list)
    expected_behavior: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Fixture:
    id: str
    title: str
    topic: str
    turns: list[FixtureTurn]


@dataclass(frozen=True)
class Chunk:
    id: str
    source_path: str
    title: str
    index: int
    content: str


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float
    term_hits: dict[str, int]


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_+-]*|[\u4e00-\u9fff]{1,2}|\d+", text.lower())
    return [token for token in tokens if token.strip()]


def load_fixture(path: Path) -> Fixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Fixture(
        id=str(data.get("id") or path.stem),
        title=str(data.get("title") or path.stem),
        topic=str(data.get("topic") or ""),
        turns=[
            FixtureTurn(
                turn=int(item["turn"]),
                question=str(item["question"]),
                expected_pages=list(item.get("expected_pages") or []),
                expected_behavior=list(item.get("expected_behavior") or []),
            )
            for item in data.get("turns", [])
        ],
    )


def resolve_input_files(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    if args.preset == "agent-architecture":
        paths.extend(AGENT_ARCHITECTURE_RAW_FILES)
    paths.extend(args.file or [])
    for directory in args.input_dir or []:
        paths.extend(sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json", ".jsonl"}))
    resolved: list[Path] = []
    missing: list[Path] = []
    for path in paths:
        expanded = path.expanduser()
        if expanded.exists() and expanded.is_file():
            resolved.append(expanded)
        else:
            missing.append(expanded)
    if missing and not args.allow_missing:
        missing_text = "\n".join(f"- {path}" for path in missing)
        raise SystemExit(f"Missing input file(s):\n{missing_text}")
    return list(dict.fromkeys(resolved))


def build_chunks(paths: list[Path], *, target_chars: int, overlap_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in paths:
        text = read_source_text(path)
        blocks = split_markdown_blocks(text) if path.suffix.lower() in {".md", ".markdown"} else split_plain_blocks(text)
        current_title = path.stem
        current = ""
        index = 0
        for title, block in blocks:
            if title:
                current_title = title
            if len(current) + len(block) + 2 <= target_chars:
                current = f"{current}\n\n{block}".strip()
                continue
            if current:
                chunks.append(Chunk(id=f"{path.name}:{index}", source_path=str(path), title=current_title, index=index, content=current))
                index += 1
                current = overlap_tail(current, overlap_chars)
            if len(block) > target_chars:
                for part in split_long_text(block, target_chars, overlap_chars):
                    chunks.append(Chunk(id=f"{path.name}:{index}", source_path=str(path), title=current_title, index=index, content=part))
                    index += 1
                current = ""
            else:
                current = f"{current}\n\n{block}".strip()
        if current:
            chunks.append(Chunk(id=f"{path.name}:{index}", source_path=str(path), title=current_title, index=index, content=current))
    return chunks


def read_source_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".json", ".jsonl"}:
        return normalize_chat_like_text(text)
    return text


def normalize_chat_like_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            lines.append(stripped)
            continue
        if isinstance(item, dict):
            role = item.get("role") or item.get("type") or item.get("source") or "record"
            content = item.get("content") or item.get("message") or item.get("text") or item.get("title") or item
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else text


def split_markdown_blocks(text: str) -> list[tuple[str | None, str]]:
    blocks: list[tuple[str | None, str]] = []
    current_title: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{1,4}\s+\S", line):
            if current:
                blocks.append((current_title, "\n".join(current).strip()))
                current = []
            current_title = line.lstrip("#").strip()
        current.append(line)
    if current:
        blocks.append((current_title, "\n".join(current).strip()))
    return [(title, block) for title, block in blocks if block]


def split_plain_blocks(text: str) -> list[tuple[str | None, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return [(None, paragraph) for paragraph in paragraphs]


def split_long_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target_chars)
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return [part for part in parts if part]


def overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return ""
    return text[-overlap_chars:].strip()


def bm25_search(chunks: list[Chunk], query: str, *, top_k: int) -> list[ScoredChunk]:
    query_terms = tokenize(query)
    if not query_terms:
        return []
    chunk_terms = [tokenize(chunk.content + "\n" + chunk.title) for chunk in chunks]
    term_counts = [Counter(terms) for terms in chunk_terms]
    doc_freq: Counter[str] = Counter()
    for terms in chunk_terms:
        doc_freq.update(set(terms))
    avg_len = sum(len(terms) for terms in chunk_terms) / max(len(chunk_terms), 1)
    k1 = 1.5
    b = 0.75
    scored: list[ScoredChunk] = []
    for chunk, terms, counts in zip(chunks, chunk_terms, term_counts, strict=True):
        score = 0.0
        hits: dict[str, int] = {}
        doc_len = max(len(terms), 1)
        for term in query_terms:
            tf = counts.get(term, 0)
            if tf <= 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (len(chunks) - df + 0.5) / (df + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(avg_len, 1)))
            hits[term] = tf
        if score > 0:
            scored.append(ScoredChunk(chunk=chunk, score=score, term_hits=hits))
    return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def answer_with_model(
    *,
    question: str,
    history: list[dict[str, str]],
    evidence: list[ScoredChunk],
    provider_name: str | None,
    config_path: Path | None,
    max_tokens: int,
) -> dict[str, Any]:
    config = load_config(config_path or default_config_path())
    selected_provider = provider_name or config.models.default_provider
    if not selected_provider:
        raise SystemExit("No model provider configured. Pass --provider or set models.default_provider.")
    provider_config = config.models.providers[selected_provider]
    gateway = ModelGateway.from_config(selected_provider, provider_config, timeout_seconds=config.models.request_timeout_seconds)
    evidence_text = "\n\n".join(
        f"[{index}] source={item.chunk.source_path} chunk={item.chunk.index} score={item.score:.4f}\n{item.chunk.content}"
        for index, item in enumerate(evidence, start=1)
    )
    history_text = "\n".join(f"{item['role']}: {item['content']}" for item in history[-10:])
    response = gateway.complete(
        ChatCompletionRequest(
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        "You are answering from a conventional chunk-based RAG baseline. "
                        "Use only the retrieved raw chunks as evidence. "
                        "Answer in Chinese. Cite chunk numbers like [1] when useful."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=f"Conversation history:\n{history_text or 'None'}\n\nRetrieved chunks:\n{evidence_text}\n\nQuestion:\n{question}",
                ),
            ],
            temperature=0.1,
            max_tokens=max_tokens,
            structured_output=False,
        )
    )
    return {
        "answer": response.content,
        "provider": response.provider,
        "model": response.model,
        "usage": response.usage,
        "elapsed_seconds": round(response.elapsed_seconds, 3),
        "tokens_per_second": response.tokens_per_second,
    }


def run_baseline(args: argparse.Namespace) -> Path:
    fixture = load_fixture(args.fixture)
    input_files = resolve_input_files(args)
    chunks = build_chunks(input_files, target_chars=args.chunk_chars, overlap_chars=args.overlap_chars)
    if not chunks:
        raise SystemExit("No chunks were created from input files.")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_root / f"rag_lite_{fixture.id}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    input_manifest = []
    raw_dir = run_dir / "raw_inputs"
    if args.copy_inputs:
        raw_dir.mkdir()
    for path in input_files:
        item = {"source": str(path), "size": path.stat().st_size}
        if args.copy_inputs:
            target = raw_dir / safe_name(path)
            shutil.copy2(path, target)
            item["copy"] = str(target)
        input_manifest.append(item)
    history: list[dict[str, str]] = []
    turn_results = []
    started = time.perf_counter()
    for turn in fixture.turns:
        evidence = bm25_search(chunks, turn.question, top_k=args.top_k)
        model_result: dict[str, Any] = {}
        if not args.retrieval_only:
            model_result = answer_with_model(
                question=turn.question,
                history=history,
                evidence=evidence,
                provider_name=args.provider,
                config_path=args.config,
                max_tokens=args.max_tokens,
            )
            history.append({"role": "user", "content": turn.question})
            history.append({"role": "assistant", "content": model_result.get("answer", "")})
        result = {
            "turn": turn.turn,
            "question": turn.question,
            "expected_pages": turn.expected_pages,
            "expected_behavior": turn.expected_behavior,
            "retrieved_chunks": [serialize_scored_chunk(item, include_content=args.store_evidence_content) for item in evidence],
            **model_result,
        }
        turn_results.append(result)
        (run_dir / f"turn_{turn.turn:02d}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "fixture": fixture.id,
        "title": fixture.title,
        "topic": fixture.topic,
        "preset": args.preset,
        "input_files": input_manifest,
        "chunk_count": len(chunks),
        "chunk_chars": args.chunk_chars,
        "overlap_chars": args.overlap_chars,
        "top_k": args.top_k,
        "retrieval_only": args.retrieval_only,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if args.store_chunk_index:
        (run_dir / "chunks.json").write_text(
            json.dumps([serialize_chunk(chunk, include_content=args.store_chunk_content) for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (run_dir / "chunk_summary.json").write_text(json.dumps(summarize_chunks(chunks), ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps({"metadata": metadata, "turns": turn_results}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(build_report(metadata, turn_results), encoding="utf-8")
    return run_dir


def serialize_chunk(chunk: Chunk, *, include_content: bool = False) -> dict[str, Any]:
    data = {"id": chunk.id, "source_path": chunk.source_path, "title": chunk.title, "index": chunk.index, "chars": len(chunk.content), "preview": chunk.content[:500]}
    if include_content:
        data["content"] = chunk.content
    return data


def serialize_scored_chunk(item: ScoredChunk, *, include_content: bool = False) -> dict[str, Any]:
    data = serialize_chunk(item.chunk, include_content=include_content)
    data.update({"score": round(item.score, 6), "term_hits": item.term_hits})
    return data


def summarize_chunks(chunks: list[Chunk]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        item = by_source.setdefault(chunk.source_path, {"source_path": chunk.source_path, "chunk_count": 0, "chars": 0})
        item["chunk_count"] += 1
        item["chars"] += len(chunk.content)
    return {"total_chunks": len(chunks), "sources": list(by_source.values())}


def safe_name(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(path).strip("/"))[-180:]


def build_report(metadata: dict[str, Any], turns: list[dict[str, Any]]) -> str:
    usage_summary = summarize_usage(turns)
    lines = [
        "# RAG-lite Baseline Report",
        "",
        f"- fixture: {metadata['fixture']}",
        f"- preset: {metadata['preset']}",
        f"- input_files: {len(metadata['input_files'])}",
        f"- chunk_count: {metadata['chunk_count']}",
        f"- chunk_chars: {metadata['chunk_chars']}",
        f"- overlap_chars: {metadata['overlap_chars']}",
        f"- top_k: {metadata['top_k']}",
        f"- retrieval_only: {metadata['retrieval_only']}",
        f"- elapsed_seconds: {metadata['elapsed_seconds']}",
        f"- total_prompt_tokens: {usage_summary['prompt_tokens']}",
        f"- total_completion_tokens: {usage_summary['completion_tokens']}",
        f"- total_tokens: {usage_summary['total_tokens']}",
        f"- prompt_cache_hit_tokens: {usage_summary['prompt_cache_hit_tokens']}",
        f"- prompt_cache_miss_tokens: {usage_summary['prompt_cache_miss_tokens']}",
        "",
        "## Input Files",
        "",
    ]
    for item in metadata["input_files"]:
        lines.append(f"- {item['source']} ({item['size']} bytes)")
    lines.extend(["", "## Turns", ""])
    for turn in turns:
        retrieved = turn.get("retrieved_chunks") or []
        lines.extend(
            [
                f"### Turn {turn['turn']}",
                "",
                f"- question: {turn['question']}",
                f"- retrieved_chunks: {len(retrieved)}",
                f"- expected_pages: {', '.join(turn.get('expected_pages') or []) or 'none'}",
                f"- provider: {turn.get('provider', 'retrieval-only')}",
                f"- model: {turn.get('model', 'n/a')}",
                f"- usage: {turn.get('usage', {})}",
                "",
                "Top chunks:",
            ]
        )
        for index, chunk in enumerate(retrieved, start=1):
            lines.append(f"- {index}. {chunk['source_path']}#{chunk['index']} score={chunk['score']} title={chunk['title']}")
        answer = str(turn.get("answer") or "").strip()
        if answer:
            lines.extend(["", "Answer preview:", "", answer[:1200]])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def summarize_usage(turns: list[dict[str, Any]]) -> dict[str, int]:
    keys = [
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ]
    summary = dict.fromkeys(keys, 0)
    for turn in turns:
        usage = turn.get("usage") or {}
        for key in keys:
            summary[key] += int(usage.get(key) or 0)
    return summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple local chunk-RAG baseline against a KnoArbor chat fixture.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--preset", choices=["agent-architecture", "none"], default="agent-architecture")
    parser.add_argument("--file", action="append", type=Path, default=[])
    parser.add_argument("--input-dir", action="append", type=Path, default=[])
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--chunk-chars", type=int, default=1600)
    parser.add_argument("--overlap-chars", type=int, default=200)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--copy-inputs", action="store_true", help="Copy raw input files into the run directory. Disabled by default to avoid huge outputs.")
    parser.add_argument("--store-chunk-index", action="store_true", help="Persist every chunk record. Disabled by default.")
    parser.add_argument("--store-chunk-content", action="store_true", help="Persist full chunk text in chunks.json. Disabled by default.")
    parser.add_argument("--store-evidence-content", action="store_true", help="Persist full retrieved chunk text in turn JSON files. Disabled by default.")
    parser.add_argument("--provider")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--max-tokens", type=int, default=1800)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    run_dir = run_baseline(parse_args(argv or sys.argv[1:]))
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
