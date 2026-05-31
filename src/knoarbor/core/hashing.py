from __future__ import annotations

import hashlib


def content_hash(source_focus: str, answer: str) -> str:
    digest = hashlib.sha256(f"{source_focus}\n\n{answer}".encode("utf-8")).hexdigest()
    return digest[:12]


def file_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
