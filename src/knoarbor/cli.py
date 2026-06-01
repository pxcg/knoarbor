from __future__ import annotations

from typing import Sequence

from knoarbor.cli_commands.parser import build_parser
from knoarbor.core.errors import describe_exception, error_hint


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        descriptor = describe_exception(exc)
        retry_hint = " retryable=true" if descriptor.retryable else ""
        hint = f"\nhint: {error_hint(descriptor.code)}"
        parser.exit(2, f"knoarbor: error: [{descriptor.code}] {descriptor.category}{retry_hint}: {descriptor.message}{hint}\n")


if __name__ == "__main__":
    raise SystemExit(main())
