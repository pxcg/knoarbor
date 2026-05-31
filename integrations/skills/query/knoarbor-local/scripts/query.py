#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def main() -> int:
    parser = argparse.ArgumentParser(description="Query a local KnoArbor service.")
    parser.add_argument("query", help="Search query to send to KnoArbor.")
    parser.add_argument("--base-url", default=os.environ.get("KNOARBOR_BASE_URL"))
    parser.add_argument("--vault", default=os.environ.get("KNOARBOR_VAULT_PATH"))
    parser.add_argument("--config", default=os.environ.get("KNOARBOR_CONFIG_PATH"))
    parser.add_argument("--mode", choices=["quick", "balanced", "deep"], default="balanced")
    parser.add_argument("--max-results", type=int, default=6)
    parser.add_argument("--page-dir", action="append", dest="page_dirs", default=[])
    parser.add_argument("--include-related", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-content", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--raw", action="store_true", help="Print raw JSON response.")
    args = parser.parse_args()

    config_path = _resolve_config_path(args.config)
    config = _load_yaml(config_path) if config_path else {}
    base_url = (args.base_url or _base_url_from_config(config) or DEFAULT_BASE_URL).rstrip("/")
    vault_path = args.vault or _vault_path_from_config(config, config_path)
    if not vault_path:
        print(
            "KnoArbor vault path is required. Set KNOARBOR_VAULT_PATH, pass --vault, "
            "or run from a project with config.yaml.",
            file=sys.stderr,
        )
        return 2

    payload = {
        "query": args.query,
        "obsidian_vault_path": str(Path(vault_path).expanduser()),
        "mode": args.mode,
        "max_results": args.max_results,
        "page_dirs": args.page_dirs,
        "include_related": args.include_related,
        "include_content": args.include_content,
        "caller": "generic-skill",
    }
    try:
        response = _post_json(f"{base_url}/query/search", payload, timeout=args.timeout)
    except urllib.error.URLError as exc:
        print(f"KnoArbor query failed: {exc}", file=sys.stderr)
        print(f"Check whether the service is running at {base_url}/health.", file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        print(_format_response(response))
    return 0


def _resolve_config_path(value: str | None) -> Path | None:
    for candidate in _config_candidates(value):
        if candidate.exists():
            return candidate.resolve()
    return None


def _config_candidates(value: str | None) -> list[Path]:
    candidates: list[Path] = []
    if value:
        candidates.append(Path(value).expanduser())
    candidates.extend(
        [
            Path.cwd() / "config.yaml",
            Path.home() / "Projects" / "KnoArbor" / "config.yaml",
        ]
    )
    return candidates


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        import yaml
    except ImportError:
        return _load_minimal_yaml(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _load_minimal_yaml(path: Path) -> dict[str, Any]:
    """Small parser for the config fields this standalone helper needs."""
    data: dict[str, Any] = {}
    section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            section = line[:-1].strip()
            data.setdefault(section, {})
            continue
        if section and raw_line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            data.setdefault(section, {})[key.strip()] = value.strip().strip("'\"")
    return data


def _base_url_from_config(config: dict[str, Any]) -> str | None:
    server = config.get("server")
    if not isinstance(server, dict):
        return None
    host = server.get("host") or "127.0.0.1"
    port = server.get("port") or 8000
    return f"http://{host}:{port}"


def _vault_path_from_config(config: dict[str, Any], config_path: Path | None) -> str | None:
    vault = config.get("vault")
    if not isinstance(vault, dict) or not vault.get("path"):
        return None
    path = Path(str(vault["path"])).expanduser()
    if not path.is_absolute() and config_path:
        path = config_path.parent / path
    return str(path.resolve())


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _format_response(response: dict[str, Any]) -> str:
    lines = [
        f"Query: {response.get('query', '')}",
        f"Retrieval mode: {response.get('retrieval_mode', '')}",
        "",
        "Results:",
    ]
    for index, result in enumerate(response.get("results", [])[:8], start=1):
        path = result.get("path", "")
        title = result.get("title", "")
        relevance = result.get("relevance", "")
        match_kind = result.get("match_kind", "")
        summary = result.get("summary", "")
        lines.append(f"{index}. {title} ({path}) [{relevance}, {match_kind}]")
        if summary:
            lines.append(f"   {summary}")
        for point in result.get("key_points", [])[:3]:
            lines.append(f"   - {point}")
    gaps = response.get("gaps") or []
    if gaps:
        lines.extend(["", "Gaps:"])
        lines.extend(f"- {gap}" for gap in gaps)
    context_pack = response.get("context_pack")
    if context_pack:
        lines.extend(["", "Context Pack:", str(context_pack)])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
