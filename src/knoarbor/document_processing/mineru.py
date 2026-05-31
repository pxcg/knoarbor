from __future__ import annotations

import json
from pathlib import Path
import uuid
from urllib import error, request

from knoarbor.core.config import MinerUDocumentProcessingConfig
from knoarbor.core.errors import DocumentPreprocessorUnavailable, ExternalServiceError, SourceNotFound
from knoarbor.document_processing.schemas import DocumentProcessingItem


class MinerUResponse:
    def __init__(self, *, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self.body = body


class MinerUDocumentProcessor:
    """Calls a user-managed MinerU-compatible service and materializes Markdown."""

    name = "mineru"

    def run(self, config: MinerUDocumentProcessingConfig) -> list[DocumentProcessingItem]:
        _validate_service_config(config)
        if not config.input_dir:
            raise DocumentPreprocessorUnavailable("document_processing.mineru.input_dir is required when MinerU processing is enabled.")

        input_dir = config.input_dir.expanduser().resolve()
        if not input_dir.exists() or not input_dir.is_dir():
            raise SourceNotFound(f"MinerU input directory does not exist: {input_dir}")

        output_dir = config.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        items: list[DocumentProcessingItem] = []
        for path in _discover_input_files(input_dir, config.patterns, config.recursive):
            try:
                response = self._post(config, path, output_dir)
                output_path = _materialize_markdown(path, output_dir, response, config)
                if output_path is None:
                    items.append(
                        DocumentProcessingItem(
                            adapter=self.name,
                            input_path=str(path),
                            status="failed",
                            reason="MinerU completed but no Markdown output was found.",
                            error_type="MissingMarkdownOutput",
                            error_message="Configure response_markdown_field/response_path_field or ensure the service writes <stem>.md.",
                        )
                    )
                    continue
                items.append(
                    DocumentProcessingItem(
                        adapter=self.name,
                        input_path=str(path),
                        output_path=str(output_path),
                        status="processed",
                        reason=f"Processed by MinerU HTTP service with status {response.status_code}.",
                    )
                )
            except Exception as exc:
                items.append(
                    DocumentProcessingItem(
                        adapter=self.name,
                        input_path=str(path),
                        status="failed",
                        reason="MinerU document processing failed.",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
        return items

    def process_file(self, config: MinerUDocumentProcessingConfig, input_path: Path) -> DocumentProcessingItem:
        _validate_service_config(config)
        path = input_path.expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise SourceNotFound(f"Document input file does not exist: {path}")

        output_dir = config.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        response = self._post(config, path, output_dir)
        output_path = _materialize_markdown(path, output_dir, response, config)
        if output_path is None:
            raise ExternalServiceError(
                "MinerU completed but no Markdown output was found. Configure "
                "response_markdown_field/response_path_field or ensure the service writes <stem>.md."
            )
        return DocumentProcessingItem(
            adapter=self.name,
            input_path=str(path),
            output_path=str(output_path),
            status="processed",
            reason=f"Processed by MinerU HTTP service with status {response.status_code}.",
        )

    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        boundary = f"knoarbor-{uuid.uuid4().hex}"
        fields = dict(config.extra_fields)
        if config.output_dir_field:
            fields[config.output_dir_field] = str(output_dir)
        if config.mode_field and config.mode:
            fields[config.mode_field] = config.mode
        body = _multipart_body(boundary, fields, file_field=config.file_field, path=path)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json,text/markdown,text/plain,*/*",
            **config.headers,
        }
        req = request.Request(config.endpoint, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=config.timeout_seconds) as response:  # noqa: S310 - user-configured local service adapter
                return MinerUResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except error.HTTPError as exc:
            raise ExternalServiceError(f"MinerU service returned HTTP {exc.code}: {exc.reason}") from exc
        except error.URLError as exc:
            raise ExternalServiceError(f"MinerU service is unavailable: {exc.reason}") from exc


def _discover_input_files(input_dir: Path, patterns: list[str], recursive: bool) -> list[Path]:
    paths: dict[Path, None] = {}
    for pattern in patterns:
        iterator = input_dir.rglob(pattern) if recursive else input_dir.glob(pattern)
        for path in iterator:
            if path.is_file():
                paths[path.resolve()] = None
    return sorted(paths)


def _validate_service_config(config: MinerUDocumentProcessingConfig) -> None:
    if not config.enabled:
        raise DocumentPreprocessorUnavailable("This file requires document preprocessing, but document_processing.mineru.enabled is false.")
    if not config.endpoint:
        raise DocumentPreprocessorUnavailable("document_processing.mineru.endpoint is required when document preprocessing is needed.")


def _multipart_body(boundary: str, fields: dict[str, object], *, file_field: str, path: Path) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'.encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def _materialize_markdown(
    input_path: Path,
    output_dir: Path,
    response: MinerUResponse,
    config: MinerUDocumentProcessingConfig,
) -> Path | None:
    payload = _json_payload(response)
    if payload is not None:
        markdown = _field_value(payload, config.response_markdown_field)
        if isinstance(markdown, str) and markdown.strip():
            return _write_markdown(output_dir / f"{input_path.stem}.md", markdown)
        markdown = _mineru_result_markdown(payload, input_path)
        if isinstance(markdown, str) and markdown.strip():
            return _write_markdown(output_dir / f"{input_path.stem}.md", markdown)
        output_path = _field_value(payload, config.response_path_field)
        if isinstance(output_path, str) and output_path.strip():
            path = Path(output_path).expanduser()
            if not path.is_absolute():
                path = output_dir / path
            if path.exists() and path.is_file():
                return path.resolve()

    content_type = response.headers.get("content-type", "")
    text = response.body.decode("utf-8", errors="replace")
    if response.body and ("markdown" in content_type or content_type.startswith("text/plain")) and text.strip():
        return _write_markdown(output_dir / f"{input_path.stem}.md", text)

    for candidate in (output_dir / f"{input_path.stem}.md", output_dir / input_path.stem / f"{input_path.stem}.md"):
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def _json_payload(response: MinerUResponse) -> dict[str, object] | None:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        return None
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _field_value(payload: dict[str, object], field: str | None) -> object:
    if not field:
        return None
    current: object = payload
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _mineru_result_markdown(payload: dict[str, object], input_path: Path) -> str | None:
    """Read native MinerU 3.x `results.<filename>.md_content` payloads."""
    results = payload.get("results")
    if not isinstance(results, dict):
        return None

    preferred_keys = [
        input_path.name,
        input_path.stem,
        f"{input_path.stem}{input_path.suffix.lower()}",
    ]
    for key in preferred_keys:
        markdown = _result_markdown(results.get(key))
        if markdown:
            return markdown

    for value in results.values():
        markdown = _result_markdown(value)
        if markdown:
            return markdown
    return None


def _result_markdown(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    markdown = value.get("md_content")
    return markdown if isinstance(markdown, str) and markdown.strip() else None


def _write_markdown(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path.resolve()
