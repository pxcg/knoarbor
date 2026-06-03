#!/usr/bin/env python3
from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from collections.abc import Callable


def main() -> int:
    """Backward-compatible query helper.

    Prefer `knoarbor.py query ...` for new integrations. This wrapper keeps the
    original skill examples and existing host-AI calls working.
    """

    knoarbor_main = _load_main()
    argv = sys.argv[1:]
    global_args, query_args = _split_global_args(argv)
    if "--check" in query_args:
        query_args = [arg for arg in query_args if arg != "--check"]
        sys.argv = [sys.argv[0], *global_args, "check", *query_args]
    elif query_args and query_args[0] in {"-h", "--help"}:
        sys.argv = [sys.argv[0], *global_args, "query", *query_args]
    else:
        sys.argv = [sys.argv[0], *global_args, "query", *query_args]
    return knoarbor_main()


def _load_main() -> Callable[[], int]:
    script_path = Path(__file__).resolve().with_name("knoarbor.py")
    spec = importlib.util.spec_from_file_location("knoarbor_skill_main", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load KnoArbor skill helper from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.main


def _split_global_args(argv: list[str]) -> tuple[list[str], list[str]]:
    value_flags = {"--base-url", "--vault", "--config", "--timeout"}
    boolean_flags = {"--raw"}
    global_args: list[str] = []
    query_args: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in value_flags and index + 1 < len(argv):
            global_args.extend([arg, argv[index + 1]])
            index += 2
            continue
        if any(arg.startswith(f"{flag}=") for flag in value_flags):
            global_args.append(arg)
            index += 1
            continue
        if arg in boolean_flags:
            global_args.append(arg)
            index += 1
            continue
        query_args.append(arg)
        index += 1
    return global_args, query_args


if __name__ == "__main__":
    raise SystemExit(main())
