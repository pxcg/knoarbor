from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENDPOINT_DIR_NAME = ".knoarbor"
ENDPOINT_FILE_NAME = "endpoint.json"
RUNTIME_DIR_ENV = "KNOARBOR_RUNTIME_DIR"


def find_available_port(host: str, preferred_port: int, *, max_attempts: int = 100) -> tuple[int, bool]:
    """Return a bindable local port, preferring the configured port."""
    for port in range(preferred_port, min(65535, preferred_port + max_attempts - 1) + 1):
        if is_port_available(host, port):
            return port, port != preferred_port
    raise RuntimeError(f"No available port found near {preferred_port}.")


def is_port_available(host: str, port: int) -> bool:
    bind_host = _bind_host(host)
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
        except OSError:
            return False
    return True


def write_runtime_endpoint(
    config_path: str | Path,
    *,
    host: str,
    port: int,
    base_url: str,
    vault_path: str | Path | None = None,
) -> Path:
    endpoint_path = runtime_endpoint_path(config_path)
    resolved_config_path = Path(config_path).expanduser().resolve()
    payload: dict[str, Any] = {
        "schema_version": "knoarbor_runtime_endpoint.v1",
        "base_url": base_url,
        "host": host,
        "port": port,
        "config_path": str(resolved_config_path),
        "vault_path": str(Path(vault_path).expanduser().resolve()) if vault_path is not None else None,
        "pid": os.getpid(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_endpoint_file(endpoint_path, payload)
    _write_endpoint_file(user_runtime_endpoint_path(), payload)
    return endpoint_path


def runtime_endpoint_path(config_path: str | Path) -> Path:
    return Path(config_path).expanduser().resolve().parent / ENDPOINT_DIR_NAME / ENDPOINT_FILE_NAME


def user_runtime_endpoint_path() -> Path:
    runtime_dir = os.environ.get(RUNTIME_DIR_ENV)
    if runtime_dir:
        return Path(runtime_dir).expanduser().resolve() / ENDPOINT_FILE_NAME
    return Path.home() / ENDPOINT_DIR_NAME / ENDPOINT_FILE_NAME


def _write_endpoint_file(endpoint_path: Path, payload: dict[str, Any]) -> None:
    endpoint_path.parent.mkdir(parents=True, exist_ok=True)
    endpoint_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _bind_host(host: str) -> str:
    if host in {"0.0.0.0", ""}:
        return "127.0.0.1"
    if host == "::":
        return "::1"
    return host
