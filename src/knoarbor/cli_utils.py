from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TextIO

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.runtime import configure_runtime_logging, runtime_logger
from knoarbor.runtime.run_monitor import read_run, read_run_events
from knoarbor.core.schemas.run_monitor import TERMINAL_RUN_STATUSES


logger = runtime_logger(__name__)


def read_json_object(path: str) -> dict[str, object]:
    input_path = Path(path).expanduser()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise UserInputError("Input JSON must be an object")
    return payload


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def print_run_metrics(metrics: dict[str, object]) -> None:
    if not metrics:
        return
    semantic = metrics.get("semantic") if isinstance(metrics.get("semantic"), dict) else {}
    assert isinstance(semantic, dict)
    print(f"elapsed_seconds: {_fmt_metric(metrics.get('elapsed_seconds'))}")
    print(f"semantic_calls: {semantic.get('semantic_call_count', 0)}")
    print(f"total_tokens: {semantic.get('total_tokens', 0)}")
    print(f"prompt_cached_tokens: {semantic.get('prompt_cached_tokens', 0)}")
    print(f"prompt_cache_hit_tokens: {semantic.get('prompt_cache_hit_tokens', 0)}")
    print(f"prompt_cache_miss_tokens: {semantic.get('prompt_cache_miss_tokens', 0)}")
    print(f"tokens_per_second: {_fmt_metric(semantic.get('tokens_per_second'))}")


def print_doctor_details(details: dict[str, object]) -> None:
    if not details:
        return
    for key, value in details.items():
        if value in (None, "", [], {}):
            continue
        print(f"  {key}: {value}")


def follow_run_events(
    vault_path: Path,
    run_id: str,
    *,
    after: int = 0,
    poll_seconds: float = 2.0,
    stream: TextIO = sys.stdout,
) -> int:
    cursor = after
    last_status_line: tuple[str, str, str | None] | None = None
    last_heartbeat_log = 0.0
    while True:
        record = read_run(vault_path, run_id)
        saw_event = False
        for event in read_run_events(vault_path, run_id, after=cursor):
            saw_event = True
            cursor = max(cursor, event.sequence)
            progress = ""
            if event.progress.total:
                progress = f" ({event.progress.completed}/{event.progress.total})"
            current = f" · {event.current_item}" if event.current_item else ""
            print(f"[{event.sequence}] {event.status} {event.stage}{progress}{current} - {event.message}", file=stream, flush=True)
        now = time.monotonic()
        if not saw_event and record.status not in TERMINAL_RUN_STATUSES:
            status_line = (record.status, record.stage, record.current_item)
            if status_line != last_status_line or now - last_heartbeat_log >= 10:
                current = f" · {record.current_item}" if record.current_item else ""
                print(
                    f"[heartbeat] {record.status} {record.stage}{current} elapsed={_fmt_metric(record.elapsed_seconds)}s - {record.message}",
                    file=stream,
                    flush=True,
                )
                last_status_line = status_line
                last_heartbeat_log = now
        if record.status in TERMINAL_RUN_STATUSES:
            print(f"run: {record.run_id} status={record.status} elapsed={_fmt_metric(record.elapsed_seconds)}s", file=stream, flush=True)
            if record.result_summary:
                print(f"summary: {json.dumps(record.result_summary, ensure_ascii=False)}", file=stream, flush=True)
            if record.error:
                print(f"error: {record.error}", file=stream, flush=True)
            return 0 if record.status == "completed" else 1
        time.sleep(poll_seconds)


def resolve_config(args: argparse.Namespace):
    config = load_config(resolve_config_path(args))
    log_path = configure_runtime_logging(config.vault.path)
    logger.info("cli_config_loaded command=%s vault=%s log=%s", getattr(args, "command", None), config.vault.path, log_path)
    return config


def resolve_config_path(args: argparse.Namespace) -> Path:
    return Path(args.config).expanduser().resolve() if args.config else default_config_path()


def resolve_vault_path(args: argparse.Namespace, config) -> Path:
    if args.vault:
        return Path(args.vault).expanduser().resolve()
    return config.vault.path


def count_raw_sources(vault_path: Path) -> int:
    raw_path = vault_path / "raw"
    if not raw_path.exists():
        return 0
    return sum(1 for path in raw_path.rglob("*") if path.is_file() and path.name != ".gitkeep")


def _fmt_metric(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return "n/a"
