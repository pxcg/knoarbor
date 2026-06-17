#!/usr/bin/env python3
"""Run a WeKnora RAG baseline against a KnoArbor chat evaluation fixture.

This script is intentionally outside the KnoArbor runtime package. It is an
evaluation harness for comparing wiki-page answers with chunk-style RAG answers.
It writes all outputs under tmp by default and never modifies a KnoArbor vault.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE = Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json")
DEFAULT_OUTPUT_ROOT = Path("tmp/rag-baselines")
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_UPLOAD_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".doc", ".docx"}


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


class WeKnoraHTTPError(RuntimeError):
    """Raised when the WeKnora API returns a non-success response."""


class WeKnoraClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        bearer_token: str | None = None,
        timeout: int = 180,
        ca_file: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.bearer_token = bearer_token or None
        self.timeout = timeout
        self.ssl_context = ssl.create_default_context(cafile=ca_file) if ca_file else None

    def login(self, email: str, password: str) -> dict[str, Any]:
        response = self.request_json("POST", "/api/v1/auth/login", {"email": email, "password": password}, authenticated=False)
        token = response.get("token") or response.get("access_token")
        if not token:
            raise WeKnoraHTTPError("Login succeeded but response did not include a bearer token.")
        self.bearer_token = str(token)
        return response

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path, query)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method.upper())
        request.add_header("Content-Type", "application/json")
        self._add_auth_headers(request, authenticated=authenticated)
        data = self._open(request)
        return parse_json_response(data)

    def upload_file(
        self,
        *,
        knowledge_base_id: str,
        file_path: Path,
        metadata: dict[str, Any] | None = None,
        channel: str = "api",
    ) -> dict[str, Any]:
        boundary = "----knoarbor-weknora-" + uuid.uuid4().hex
        fields: dict[str, str] = {"channel": channel}
        if metadata:
            fields["metadata"] = json.dumps(metadata, ensure_ascii=False)
        body = build_multipart_body(boundary=boundary, fields=fields, file_field="file", file_path=file_path)
        request = urllib.request.Request(
            self._url(f"/api/v1/knowledge-bases/{knowledge_base_id}/knowledge/file"),
            data=body,
            method="POST",
        )
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        self._add_auth_headers(request, authenticated=True)
        data = self._open(request)
        return parse_json_response(data)

    def stream_chat(self, *, session_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        request = urllib.request.Request(
            self._url(f"/api/v1/knowledge-chat/{session_id}"),
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        self._add_auth_headers(request, authenticated=True)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                return parse_sse_bytes(response.read())
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise WeKnoraHTTPError(f"HTTP {error.code} {request.full_url}: {body}") from error
        except urllib.error.URLError as error:
            raise WeKnoraHTTPError(f"Request failed {request.full_url}: {error}") from error

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        url = self.base_url + path
        if query:
            encoded = urllib.parse.urlencode({key: value for key, value in query.items() if value is not None})
            if encoded:
                url += "?" + encoded
        return url

    def _add_auth_headers(self, request: urllib.request.Request, *, authenticated: bool) -> None:
        if not authenticated:
            return
        if self.api_key:
            request.add_header("X-API-Key", self.api_key)
        if self.bearer_token:
            request.add_header("Authorization", f"Bearer {self.bearer_token}")

    def _open(self, request: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise WeKnoraHTTPError(f"HTTP {error.code} {request.full_url}: {body}") from error
        except urllib.error.URLError as error:
            raise WeKnoraHTTPError(f"Request failed {request.full_url}: {error}") from error


def parse_json_response(data: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as error:
        preview = data[:500].decode("utf-8", errors="replace")
        raise WeKnoraHTTPError(f"Response is not JSON: {preview}") from error
    if isinstance(decoded, dict) and decoded.get("success") is False:
        raise WeKnoraHTTPError(decoded.get("message") or decoded.get("code") or "WeKnora API returned success=false.")
    if isinstance(decoded, dict) and "data" in decoded:
        data_value = decoded["data"]
        if isinstance(data_value, dict):
            return data_value
        return {"items": data_value, "total": decoded.get("total")}
    if isinstance(decoded, dict):
        return decoded
    return {"items": decoded}


def parse_sse_bytes(data: bytes) -> list[dict[str, Any]]:
    return parse_sse_lines(data.decode("utf-8", errors="replace").splitlines())


def parse_sse_lines(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    buffer: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if buffer:
                events.append(parse_sse_event("\n".join(buffer)))
                buffer = []
            continue
        if line.startswith("data:"):
            buffer.append(line[5:].lstrip())
    if buffer:
        events.append(parse_sse_event("\n".join(buffer)))
    return events


def parse_sse_event(payload: str) -> dict[str, Any]:
    if payload == "[DONE]":
        return {"response_type": "complete", "done": True}
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {"response_type": "raw", "content": payload}
    return decoded if isinstance(decoded, dict) else {"response_type": "raw", "content": decoded}


def build_multipart_body(*, boundary: str, fields: dict[str, str], file_field: str, file_path: Path) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks)


def load_fixture(path: Path) -> Fixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = [
        FixtureTurn(
            turn=int(item["turn"]),
            question=str(item["question"]),
            expected_pages=list(item.get("expected_pages") or []),
            expected_behavior=list(item.get("expected_behavior") or []),
        )
        for item in data.get("turns", [])
    ]
    if not turns:
        raise ValueError(f"Fixture has no turns: {path}")
    return Fixture(
        id=str(data.get("id") or path.stem),
        title=str(data.get("title") or path.stem),
        topic=str(data.get("topic") or ""),
        turns=turns,
    )


def collect_upload_files(paths: list[Path], suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in suffixes:
            files.append(path)
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not any(part.startswith(".") for part in child.parts) and child.suffix.lower() in suffixes:
                    files.append(child)
    return sorted(dict.fromkeys(files))


def create_knowledge_base(
    client: WeKnoraClient,
    *,
    name: str,
    description: str,
    embedding_model_id: str | None,
    summary_model_id: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "chunking_config": {
            "chunk_size": 500,
            "chunk_overlap": 80,
            "separators": ["\n\n", "\n", ". ", "。", "? ", "？", "! ", "！"],
        },
    }
    if embedding_model_id:
        payload["embedding_model_id"] = embedding_model_id
    if summary_model_id:
        payload["summary_model_id"] = summary_model_id
    return client.request_json("POST", "/api/v1/knowledge-bases", payload)


def wait_for_knowledge_processing(
    client: WeKnoraClient,
    *,
    knowledge_base_id: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    started = time.time()
    last_items: list[dict[str, Any]] = []
    while True:
        response = client.request_json(
            "GET",
            f"/api/v1/knowledge-bases/{knowledge_base_id}/knowledge",
            query={"page": 1, "page_size": 200},
        )
        items = list(response.get("items") or [])
        last_items = [item for item in items if isinstance(item, dict)]
        statuses = {str(item.get("parse_status") or "").lower() for item in last_items}
        active_statuses = {status for status in statuses if status in {"pending", "processing", "parsing", "queued", "running"}}
        if not active_statuses:
            return {"items": last_items, "elapsed_seconds": round(time.time() - started, 3), "statuses": sorted(statuses)}
        if time.time() - started > timeout_seconds:
            return {
                "items": last_items,
                "elapsed_seconds": round(time.time() - started, 3),
                "statuses": sorted(statuses),
                "timed_out": True,
            }
        time.sleep(poll_seconds)


def create_session(client: WeKnoraClient, *, title: str) -> dict[str, Any]:
    return client.request_json("POST", "/api/v1/sessions", {"title": title, "description": "KnoArbor RAG baseline evaluation"})


def ask_turn(
    client: WeKnoraClient,
    *,
    session_id: str,
    knowledge_base_id: str,
    question: str,
    summary_model_id: str | None,
    channel: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": question,
        "knowledge_base_ids": [knowledge_base_id],
        "knowledge_ids": [],
        "agent_enabled": False,
        "web_search_enabled": False,
        "disable_title": True,
        "channel": channel,
    }
    if summary_model_id:
        payload["summary_model_id"] = summary_model_id
    started = time.time()
    events = client.stream_chat(session_id=session_id, payload=payload)
    elapsed = round(time.time() - started, 3)
    answer = "".join(str(event.get("content") or "") for event in events if event.get("response_type") == "answer")
    references = collect_references(events)
    return {
        "question": question,
        "answer": answer,
        "references": references,
        "events": events,
        "elapsed_seconds": elapsed,
        "event_count": len(events),
    }


def collect_references(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    references: list[dict[str, Any]] = []
    for event in events:
        raw_refs = event.get("knowledge_references") or []
        if not isinstance(raw_refs, list):
            continue
        for ref in raw_refs:
            if not isinstance(ref, dict):
                continue
            key = str(ref.get("id") or f"{ref.get('knowledge_id')}:{ref.get('chunk_index')}:{ref.get('content')[:80]}")
            if key in seen:
                continue
            seen.add(key)
            references.append(ref)
    return references


def write_turn_result(run_dir: Path, turn: FixtureTurn, result: dict[str, Any]) -> None:
    payload = {
        "turn": turn.turn,
        "question": turn.question,
        "expected_pages": turn.expected_pages,
        "expected_behavior": turn.expected_behavior,
        **result,
    }
    (run_dir / f"turn_{turn.turn:02d}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_report(*, fixture: Fixture, run_metadata: dict[str, Any], turn_results: list[dict[str, Any]]) -> str:
    lines = [
        "# WeKnora RAG Baseline Report",
        "",
        f"- fixture: {fixture.id}",
        f"- title: {fixture.title}",
        f"- topic: {fixture.topic}",
        f"- base_url: {run_metadata.get('base_url')}",
        f"- knowledge_base_id: {run_metadata.get('knowledge_base_id')}",
        f"- session_id: {run_metadata.get('session_id')}",
        f"- started_at: {run_metadata.get('started_at')}",
        f"- finished_at: {run_metadata.get('finished_at')}",
        f"- elapsed_seconds: {run_metadata.get('elapsed_seconds')}",
        "",
        "## Turn Summary",
        "",
    ]
    for result in turn_results:
        references = result.get("references") or []
        answer = str(result.get("answer") or "").strip().replace("\n", " ")
        lines.extend(
            [
                f"### Turn {result['turn']}",
                "",
                f"- question: {result['question']}",
                f"- elapsed_seconds: {result.get('elapsed_seconds')}",
                f"- event_count: {result.get('event_count')}",
                f"- reference_count: {len(references)}",
                f"- expected_pages: {', '.join(result.get('expected_pages') or []) or 'none'}",
                f"- answer_preview: {answer[:500] or 'empty'}",
                "",
                "Top references:",
            ]
        )
        for index, ref in enumerate(references[:8], start=1):
            title = ref.get("knowledge_title") or ref.get("knowledge_filename") or ref.get("knowledge_id") or "unknown"
            score = ref.get("score")
            chunk_index = ref.get("chunk_index")
            content = str(ref.get("content") or "").replace("\n", " ")[:180]
            lines.append(f"- {index}. {title} · chunk={chunk_index} · score={score} · {content}")
        if not references:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a WeKnora RAG baseline for a KnoArbor chat fixture.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--base-url", default=os.getenv("WEKNORA_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.getenv("WEKNORA_API_KEY"))
    parser.add_argument("--bearer-token", default=os.getenv("WEKNORA_BEARER_TOKEN"))
    parser.add_argument("--email", default=os.getenv("WEKNORA_EMAIL"))
    parser.add_argument("--password", default=os.getenv("WEKNORA_PASSWORD"))
    parser.add_argument("--ca-file", default=os.getenv("WEKNORA_CA_FILE"))
    parser.add_argument("--knowledge-base-id", default=os.getenv("WEKNORA_KNOWLEDGE_BASE_ID"))
    parser.add_argument("--knowledge-base-name", default="")
    parser.add_argument("--create-knowledge-base", action="store_true")
    parser.add_argument("--embedding-model-id", default=os.getenv("WEKNORA_EMBEDDING_MODEL_ID"))
    parser.add_argument("--summary-model-id", default=os.getenv("WEKNORA_SUMMARY_MODEL_ID"))
    parser.add_argument("--upload-dir", action="append", type=Path, default=[])
    parser.add_argument("--file", action="append", type=Path, default=[])
    parser.add_argument("--suffix", action="append", default=[])
    parser.add_argument("--wait-processing", action="store_true")
    parser.add_argument("--processing-timeout", type=int, default=900)
    parser.add_argument("--processing-poll", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--channel", default="api")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    fixture = load_fixture(args.fixture)
    started = time.time()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_root / f"weknora_{fixture.id}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    client = WeKnoraClient(
        base_url=args.base_url,
        api_key=args.api_key,
        bearer_token=args.bearer_token,
        timeout=args.timeout,
        ca_file=args.ca_file,
    )
    if args.email and args.password and not (args.api_key or args.bearer_token):
        login = client.login(args.email, args.password)
        (run_dir / "login.json").write_text(json.dumps(login, ensure_ascii=False, indent=2), encoding="utf-8")

    knowledge_base_id = args.knowledge_base_id
    uploads: list[dict[str, Any]] = []
    if args.create_knowledge_base:
        name = args.knowledge_base_name or f"KnoArbor RAG Baseline {run_id}"
        kb = create_knowledge_base(
            client,
            name=name,
            description=f"RAG baseline for KnoArbor fixture {fixture.id}",
            embedding_model_id=args.embedding_model_id,
            summary_model_id=args.summary_model_id,
        )
        knowledge_base_id = str(kb.get("id") or "")
        (run_dir / "knowledge_base.json").write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    if not knowledge_base_id:
        raise SystemExit("Missing knowledge base. Pass --knowledge-base-id or --create-knowledge-base.")

    suffixes = {suffix.lower() if suffix.startswith(".") else "." + suffix.lower() for suffix in args.suffix} or DEFAULT_UPLOAD_SUFFIXES
    upload_files = collect_upload_files([*args.upload_dir, *args.file], suffixes)
    for file_path in upload_files:
        uploaded = client.upload_file(
            knowledge_base_id=knowledge_base_id,
            file_path=file_path,
            metadata={"source_path": str(file_path), "baseline_fixture": fixture.id},
            channel=args.channel,
        )
        uploads.append({"file": str(file_path), "response": uploaded})
    if uploads:
        (run_dir / "uploads.json").write_text(json.dumps(uploads, ensure_ascii=False, indent=2), encoding="utf-8")
    processing: dict[str, Any] | None = None
    if args.wait_processing:
        processing = wait_for_knowledge_processing(
            client,
            knowledge_base_id=knowledge_base_id,
            timeout_seconds=args.processing_timeout,
            poll_seconds=args.processing_poll,
        )
        (run_dir / "processing.json").write_text(json.dumps(processing, ensure_ascii=False, indent=2), encoding="utf-8")

    session = create_session(client, title=f"KnoArbor RAG baseline {fixture.id} {run_id}")
    session_id = str(session.get("id") or "")
    if not session_id:
        raise SystemExit("WeKnora session creation did not return an id.")

    turn_results: list[dict[str, Any]] = []
    for turn in fixture.turns:
        result = ask_turn(
            client,
            session_id=session_id,
            knowledge_base_id=knowledge_base_id,
            question=turn.question,
            summary_model_id=args.summary_model_id,
            channel=args.channel,
        )
        result_with_fixture = {
            "turn": turn.turn,
            "question": turn.question,
            "expected_pages": turn.expected_pages,
            "expected_behavior": turn.expected_behavior,
            **result,
        }
        turn_results.append(result_with_fixture)
        write_turn_result(run_dir, turn, result)

    finished = time.time()
    metadata = {
        "fixture": fixture.id,
        "base_url": args.base_url,
        "knowledge_base_id": knowledge_base_id,
        "session_id": session_id,
        "started_at": datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "finished_at": datetime.fromtimestamp(finished).isoformat(timespec="seconds"),
        "elapsed_seconds": round(finished - started, 3),
        "uploaded_files": len(upload_files),
        "processing": processing,
    }
    (run_dir / "result.json").write_text(
        json.dumps({"metadata": metadata, "turns": turn_results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(build_report(fixture=fixture, run_metadata=metadata, turn_results=turn_results), encoding="utf-8")
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
