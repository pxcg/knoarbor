from __future__ import annotations

import json

from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin


def long_markdown_text() -> str:
    sections = [
        ("Agent Loop Overview", "Agent loops coordinate observe, reason, act, and feedback."),
        ("Workflow Boundaries", "Workflows constrain agent behavior with deterministic execution boundaries."),
        ("Evaluation Harness", "Golden fixtures keep prompt, schema, and report behavior reviewable."),
    ]
    return "\n\n".join(
        f"## {title}\n\n" + "\n".join(f"{sentence} Example {index:02d}." for index in range(18))
        for title, sentence in sections
    )


def codex_chat_payload() -> dict[str, object]:
    turns = []
    for turn_index, topic in enumerate(["agent loop", "workflow boundary", "golden harness"]):
        turns.append(
            {
                "raw_index": turn_index * 2,
                "role": "user",
                "content": f"Explain {topic} for KnoArbor.",
            }
        )
        turns.append(
            {
                "raw_index": turn_index * 2 + 1,
                "role": "assistant",
                "content": " ".join(
                    [
                        f"{topic} keeps the system structured and auditable.",
                        "It should remain grounded in source evidence.",
                    ]
                    * 14
                ),
            }
        )
    return {"session_id": "codex-golden-session", "turns": turns}


def long_markdown_source_document() -> SourceDocument:
    return SourceDocument(
        source_id="markdown:golden-long-note",
        source_type="markdown",
        origin=SourceOrigin(connector="markdown", uri="file:///raw/inbox/notes/long-agent-loop.md", raw_path="raw/inbox/notes/long-agent-loop.md"),
        content=SourceContent(format="markdown", text=long_markdown_text()),
        metadata={"title": "Long Agent Loop Note"},
        fingerprint=SourceFingerprint(content_hash="golden-long-note", connector_version="markdown@1"),
    )


def codex_chat_source_document() -> SourceDocument:
    return SourceDocument(
        source_id="codex:golden-session",
        source_type="codex_chat",
        origin=SourceOrigin(connector="codex", uri="file:///raw/inbox/chats/codex-golden-session.json", raw_path="raw/inbox/chats/codex-golden-session.json"),
        content=SourceContent(format="json", text=json.dumps(codex_chat_payload(), ensure_ascii=False, indent=2)),
        metadata={"title": "Codex Golden Session"},
        fingerprint=SourceFingerprint(content_hash="golden-codex-session", connector_version="codex@1"),
    )
