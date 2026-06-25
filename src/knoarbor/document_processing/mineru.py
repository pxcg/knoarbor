from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
import uuid
from urllib import error, request

from knoarbor.core.attachments import (
    dedupe_attachments,
    discover_markdown_image_attachments,
    normalize_attachment,
    write_attachment_sidecar,
)
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
                attachments = _discover_output_attachments(path, output_path, output_dir, response)
                write_attachment_sidecar(output_path, attachments, source=self.name)
                items.append(
                    DocumentProcessingItem(
                        adapter=self.name,
                        input_path=str(path),
                        output_path=str(output_path),
                        status="processed",
                        reason=f"Processed by MinerU HTTP service with status {response.status_code}.",
                        attachments=attachments,
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
        _materialize_payload_images(output_path, response)
        attachments = _discover_output_attachments(path, output_path, output_dir, response)
        write_attachment_sidecar(output_path, attachments, source=self.name)
        return DocumentProcessingItem(
            adapter=self.name,
            input_path=str(path),
            output_path=str(output_path),
            status="processed",
            reason=f"Processed by MinerU HTTP service with status {response.status_code}.",
            attachments=attachments,
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


def _discover_output_attachments(
    input_path: Path,
    markdown_path: Path,
    output_dir: Path,
    response: MinerUResponse,
) -> list[dict[str, object]]:
    _materialize_payload_images(markdown_path, response)
    attachments: list[dict[str, object]] = []
    attachments.extend(_payload_image_attachments(markdown_path, response))
    attachments.extend(discover_markdown_image_attachments(markdown_path))
    attachments.extend(_output_directory_image_attachments(input_path, markdown_path, output_dir))
    return dedupe_attachments(attachments)


def _output_directory_image_attachments(input_path: Path, markdown_path: Path, output_dir: Path) -> list[dict[str, object]]:
    candidate_dirs = [
        markdown_path.parent / "images",
        markdown_path.parent / input_path.stem / "images",
        output_dir / input_path.stem / "images",
        output_dir / input_path.stem / "auto" / "images",
        output_dir / input_path.stem / "hybrid_auto" / "images",
        output_dir / input_path.stem / "hybrid-engine" / "images",
        output_dir / input_path.stem / "vlm-engine" / "images",
    ]
    attachments: list[dict[str, object]] = []
    for directory in candidate_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for image_path in sorted(path for path in directory.rglob("*") if path.is_file()):
            attachments.append(
                normalize_attachment(
                    image_path,
                    base_dir=markdown_path.parent,
                    name=image_path.name,
                    source="mineru_output_dir",
                )
            )
    return attachments


def _materialize_payload_images(markdown_path: Path, response: MinerUResponse) -> None:
    payload = _json_payload(response)
    if payload is None:
        return
    results = payload.get("results")
    if not isinstance(results, dict):
        return
    for result in results.values():
        if not isinstance(result, dict):
            continue
        images = result.get("images")
        if not isinstance(images, dict):
            continue
        for name, value in images.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in {".apng", ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
                continue
            image_bytes = _decode_image_payload(value)
            if not image_bytes:
                continue
            image_path = (markdown_path.parent / "images" / name).resolve()
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)


def _decode_image_payload(value: str) -> bytes | None:
    data = value.strip()
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _payload_image_attachments(markdown_path: Path, response: MinerUResponse) -> list[dict[str, object]]:
    payload = _json_payload(response)
    if payload is None:
        return []
    attachments: list[dict[str, object]] = []
    for item in _iter_payload_image_items(payload):
        path_value = _payload_path_value(item)
        if not path_value:
            continue
        image_path = Path(path_value).expanduser()
        if not image_path.is_absolute():
            image_path = markdown_path.parent / image_path
        if not image_path.exists() or not image_path.is_file():
            continue
        attachments.append(
            normalize_attachment(
                image_path,
                base_dir=markdown_path.parent,
                name=str(item.get("name") or image_path.name),
                description=_payload_image_description(item),
                source="mineru_response",
                metadata={key: value for key, value in item.items() if key not in {"path", "image_path", "img_path", "url", "src"}},
            )
        )
    return attachments


def _payload_image_description(item: dict[str, object]) -> str:
    for key in ("caption", "description", "alt", "image_caption"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts = [part.strip() for part in value if isinstance(part, str) and part.strip()]
            if parts:
                return " ".join(parts)
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        subtype = str(item.get("sub_type") or "").strip()
        if subtype:
            return f"{subtype} extraction is available in attachment metadata."
        return "Image extraction is available in attachment metadata."
    return ""


def _iter_payload_image_items(value: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if isinstance(value, dict):
        if _payload_path_value(value):
            items.append(value)
        for child in value.values():
            items.extend(_iter_payload_image_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_iter_payload_image_items(child))
    elif isinstance(value, str):
        nested = _json_string_payload(value)
        if nested is not None:
            items.extend(_iter_payload_image_items(nested))
    return items


def _json_string_payload(value: str) -> object | None:
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _payload_path_value(item: dict[str, object]) -> str | None:
    for key in ("image_path", "img_path", "path", "url", "src"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            suffix = Path(value.split("#", 1)[0].split("?", 1)[0]).suffix.lower()
            if suffix in {".apng", ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
                return value.strip()
    return None
