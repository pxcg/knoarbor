#!/usr/bin/env python3
"""Run the fixed LLM-Wiki vs chunk-RAG chat evaluation protocol.

Default behavior is a dry plan. Real model calls only happen when --run-llmwiki
or --run-rag is provided.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from knoarbor.core.config import default_config_path  # noqa: E402
from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest  # noqa: E402
from knoarbor.services import ApplicationServices  # noqa: E402


DEFAULT_FIXTURE = Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json")
DEFAULT_RAG_SOURCE_DIR = Path("~/Documents/Obsidian/Notes/02 AI Agent")
DEFAULT_RAG_FILENAMES = ("Agent.md", "MCP.md", "OpenClaw架构.md")
DEFAULT_OUTPUT_ROOT = Path("tmp/eval-protocol")
DEFAULT_LLMWIKI_VAULT_ID = "agent-engineering"
DEFAULT_PROVIDERS = ("deepseek", "qwen37-plus")


@dataclass(frozen=True)
class EvalRun:
    label: str
    provider: str
    kind: str
    path: Path


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rag_source_files(source_dir: Path) -> list[Path]:
    base = source_dir.expanduser()
    return [base / name for name in DEFAULT_RAG_FILENAMES]


def run_llmwiki_chat(
    *,
    fixture_path: Path,
    provider: str,
    vault_id: str,
    config_path: Path | None,
    output_root: Path,
) -> Path:
    fixture = load_fixture(fixture_path)
    services = ApplicationServices()
    session_id: str | None = None
    turn_results: list[dict[str, Any]] = []
    started = time.perf_counter()

    for turn in fixture["turns"]:
        request = ChatRequest(
            config_path=str(config_path) if config_path else None,
            vault_id=vault_id,
            messages=[ChatMessageItem(role="user", content=str(turn["question"]))],
            session_id=session_id,
            provider=provider,
            append_ledger=False,
            include_trace=True,
        )
        response = services.chat.chat(request, services)
        session_id = response.session_id
        result = {
            "fixture_id": fixture["id"],
            "turn": turn["turn"],
            "question": turn["question"],
            "expected_pages": turn.get("expected_pages", []),
            "expected_behavior": turn.get("expected_behavior", []),
            "answer": response.answer,
            "answer_chars": len(response.answer),
            "citations": [item.model_dump() for item in response.citations],
            "citation_paths": [item.path for item in response.citations if item.path],
            "hidden_evidence_count": response.hidden_evidence_count,
            "citation_warnings": response.citation_warnings,
            "tool_trace": [item.model_dump() for item in response.tool_trace],
            "tool_call_count": len(response.tool_trace),
            "events": [item.model_dump() for item in response.events],
            "stats": response.stats,
            "elapsed_seconds": response.stats.get("elapsed_seconds"),
            "session_id": response.session_id,
        }
        turn_results.append(result)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / "llmwiki" / f"{provider}_{vault_id}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fixture": fixture["id"],
        "provider": provider,
        "vault_id": vault_id,
        "session_id": session_id,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "turn_count": len(turn_results),
        "total_tokens": sum(turn_usage(turn).get("total_tokens", 0) for turn in turn_results),
        "total_tool_calls": sum(turn.get("tool_call_count", 0) for turn in turn_results),
        "turns": turn_results,
    }
    for turn in turn_results:
        (run_dir / f"turn_{int(turn['turn']):02d}.json").write_text(json.dumps(turn, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(build_llmwiki_report(payload), encoding="utf-8")
    return run_dir


def run_rag_lite(
    *,
    fixture_path: Path,
    provider: str,
    source_dir: Path,
    config_path: Path | None,
    output_root: Path,
) -> Path:
    module = load_rag_lite_module()
    args = argparse.Namespace(
        fixture=fixture_path,
        output_root=output_root / "rag-lite",
        preset="none",
        file=rag_source_files(source_dir),
        input_dir=[],
        allow_missing=False,
        chunk_chars=1600,
        overlap_chars=200,
        top_k=8,
        retrieval_only=False,
        copy_inputs=False,
        store_chunk_index=False,
        store_chunk_content=False,
        store_evidence_content=False,
        provider=provider,
        config=config_path,
        max_tokens=1800,
    )
    return module.run_baseline(args)


def load_rag_lite_module() -> Any:
    path = Path(__file__).with_name("rag_lite_baseline.py")
    spec = importlib.util.spec_from_file_location("rag_lite_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_llmwiki_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Chat Eval Report - {payload['fixture']}",
        "",
        f"- provider: {payload['provider']}",
        f"- vault_id: {payload['vault_id']}",
        f"- session_id: {payload['session_id']}",
        f"- elapsed_seconds: {payload['elapsed_seconds']}",
        f"- turn_count: {payload['turn_count']}",
        f"- total_tokens: {payload['total_tokens']}",
        f"- total_tool_calls: {payload['total_tool_calls']}",
        "",
        "## Turns",
        "",
    ]
    for turn in payload["turns"]:
        citations = ", ".join(turn.get("citation_paths") or []) or "none"
        tools = ", ".join(item.get("tool", "") for item in turn.get("tool_trace", []) if item.get("tool")) or "none"
        usage = turn_usage(turn)
        lines.extend(
            [
                f"### Turn {turn['turn']}",
                "",
                f"- question: {turn['question']}",
                f"- elapsed_seconds: {turn.get('elapsed_seconds')}",
                f"- tokens: {usage.get('total_tokens', 0)}",
                f"- tools: {tools}",
                f"- citations: {citations}",
                f"- hidden_evidence_count: {turn.get('hidden_evidence_count', 0)}",
                f"- answer_chars: {turn.get('answer_chars', 0)}",
                "",
                "Answer preview:",
                "",
                preview_text(turn.get("answer", ""), 1600),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_comparison_report(runs: list[EvalRun], output_root: Path) -> Path:
    loaded = [(run, json.loads((run.path / "result.json").read_text(encoding="utf-8"))) for run in runs]
    report_dir = output_root / "comparison"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"llmwiki_rag_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Fixed LLM-Wiki vs Markdown Chunk-RAG Evaluation",
        "",
        f"- created_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- fixture: `{DEFAULT_FIXTURE}`",
        f"- LLM-Wiki vault: `{DEFAULT_LLMWIKI_VAULT_ID}`",
        f"- RAG raw files: {', '.join(DEFAULT_RAG_FILENAMES)}",
        "",
        "## Aggregate Metrics",
        "",
        "| Run | Evidence | Elapsed | Total tokens | Prompt | Completion | Tool calls |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for run, payload in loaded:
        turns = payload["turns"]
        usage = total_usage(turns)
        elapsed = payload.get("elapsed_seconds") or payload.get("metadata", {}).get("elapsed_seconds") or 0
        tool_calls = payload.get("total_tool_calls", 0)
        evidence = "wiki pages" if run.kind == "llmwiki" else f"raw chunks ({payload.get('metadata', {}).get('chunk_count')} chunks)"
        lines.append(
            f"| {run.label} | {evidence} | {float(elapsed):.2f}s | {usage['total_tokens']:,} | "
            f"{usage['prompt_tokens']:,} | {usage['completion_tokens']:,} | {tool_calls} |"
        )
    lines.extend(["", "## Retrieval Shape", ""])
    lines.extend(["| Turn | Question | " + " | ".join(run.label for run, _ in loaded) + " |", "|---:|---|" + "|".join("---" for _ in loaded) + "|"])
    max_turns = max(len(payload["turns"]) for _, payload in loaded)
    for index in range(max_turns):
        question = next((payload["turns"][index]["question"] for _, payload in loaded if index < len(payload["turns"])), "")
        cells = []
        for run, payload in loaded:
            if index >= len(payload["turns"]):
                cells.append("n/a")
            elif run.kind == "llmwiki":
                cells.append("<br>".join(payload["turns"][index].get("citation_paths") or []) or "none")
            else:
                cells.append(rag_top_chunks(payload["turns"][index]))
        lines.append(f"| {index + 1} | {question} | " + " | ".join(cells) + " |")
    lines.extend(["", "## Source Result Folders", ""])
    for run, _ in loaded:
        lines.append(f"- {run.label}: `{run.path}`")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def turn_usage(turn: dict[str, Any]) -> dict[str, int]:
    usage = (turn.get("stats") or {}).get("usage") if "stats" in turn else turn.get("usage")
    usage = usage or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def total_usage(turns: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for turn in turns:
        usage = turn_usage(turn)
        for key in summary:
            summary[key] += usage[key]
    return summary


def rag_top_chunks(turn: dict[str, Any]) -> str:
    chunks = []
    for item in turn.get("retrieved_chunks", [])[:3]:
        chunks.append(f"{Path(item['source_path']).name}#{item['index']}")
    return "<br>".join(chunks) or "none"


def preview_text(text: str, limit: int) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def print_plan(args: argparse.Namespace) -> None:
    source_files = rag_source_files(args.rag_source_dir)
    print("Fixed evaluation protocol")
    print(f"- fixture: {args.fixture}")
    print(f"- providers: {', '.join(args.provider)}")
    print(f"- llmwiki vault_id: {args.llmwiki_vault_id}")
    print("- rag files:")
    for path in source_files:
        print(f"  - {path.expanduser()}")
    print(f"- output_root: {args.output_root}")
    print("")
    print("Examples:")
    print("  uv run python scripts/eval/llmwiki_rag_comparison.py --plan")
    print("  uv run python scripts/eval/llmwiki_rag_comparison.py --run-rag --provider deepseek")
    print("  uv run python scripts/eval/llmwiki_rag_comparison.py --run-llmwiki --provider deepseek --llmwiki-vault-id agent-engineering")
    print("  uv run python scripts/eval/llmwiki_rag_comparison.py --run-rag --run-llmwiki --provider deepseek --provider qwen37-plus --compare")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed KnoArbor LLM-Wiki vs chunk-RAG evaluation protocol.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--provider", action="append", choices=DEFAULT_PROVIDERS, default=[])
    parser.add_argument("--llmwiki-vault-id", default=DEFAULT_LLMWIKI_VAULT_ID)
    parser.add_argument("--rag-source-dir", type=Path, default=DEFAULT_RAG_SOURCE_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-llmwiki", action="store_true")
    parser.add_argument("--run-rag", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--plan", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.provider:
        args.provider = list(DEFAULT_PROVIDERS)
    if args.plan or not (args.run_llmwiki or args.run_rag):
        print_plan(args)
        return 0
    config_path = args.config or default_config_path()
    runs: list[EvalRun] = []
    for provider in args.provider:
        if args.run_llmwiki:
            path = run_llmwiki_chat(
                fixture_path=args.fixture,
                provider=provider,
                vault_id=args.llmwiki_vault_id,
                config_path=config_path,
                output_root=args.output_root,
            )
            print(f"llmwiki {provider}: {path}")
            runs.append(EvalRun(label=f"LLM-Wiki / {provider}", provider=provider, kind="llmwiki", path=path))
        if args.run_rag:
            path = run_rag_lite(
                fixture_path=args.fixture,
                provider=provider,
                source_dir=args.rag_source_dir,
                config_path=config_path,
                output_root=args.output_root,
            )
            print(f"rag-lite {provider}: {path}")
            runs.append(EvalRun(label=f"RAG-lite / {provider}", provider=provider, kind="rag", path=path))
    if args.compare and len(runs) >= 2:
        print(f"comparison: {build_comparison_report(runs, args.output_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
