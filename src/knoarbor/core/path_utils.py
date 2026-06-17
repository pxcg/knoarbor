from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


def file_uri_to_path_string(uri: str, *, platform: str | None = None) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI, got: {uri}")

    platform_name = platform or os.name
    host = unquote(parsed.netloc or "")
    path = unquote(parsed.path or "")

    if platform_name == "nt":
        windows_path = path.replace("/", "\\")
        if host and host.lower() != "localhost":
            return f"\\\\{host}{windows_path}"
        if len(windows_path) >= 3 and windows_path[0] == "\\" and windows_path[2] == ":":
            windows_path = windows_path[1:]
        return windows_path

    if host and host.lower() != "localhost":
        return f"//{host}{path}"
    return path


def path_from_file_uri(uri: str) -> Path:
    return Path(file_uri_to_path_string(uri)).expanduser().resolve()
