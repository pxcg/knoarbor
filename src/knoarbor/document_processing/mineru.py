from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import io
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import socket
import stat
import uuid
from urllib import error, request
from urllib.parse import urlsplit, urlunsplit
import zipfile

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

        items: list[DocumentProcessingItem] = []
        for path in _discover_input_files(input_dir, config.patterns, config.recursive):
            try:
                items.append(self.process_file(config, path, input_root=input_dir))
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

    def process_file(
        self,
        config: MinerUDocumentProcessingConfig,
        input_path: Path,
        *,
        input_root: Path | None = None,
    ) -> DocumentProcessingItem:
        _validate_service_config(config)
        path = input_path.expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise SourceNotFound(f"Document input file does not exist: {path}")

        output_dir = config.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        source_output_dir = _source_output_dir(output_dir, path, input_root)
        source_output_dir.mkdir(parents=True, exist_ok=True)
        response = self._post(config, path, source_output_dir)
        output_path = _materialize_markdown(path, source_output_dir, response, config)
        if output_path is None:
            raise ExternalServiceError(
                "MinerU completed but no Markdown output was found. Configure "
                "response_markdown_field/response_path_field or ensure the service writes <stem>.md."
            )
        attachments = _discover_output_attachments(path, output_path, source_output_dir, response)
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
            "Accept": "application/json,application/zip,text/markdown,text/plain,*/*",
            **config.headers,
        }
        req = request.Request(config.endpoint, data=body, headers=headers, method="POST")
        try:
            with _urlopen(req, timeout_seconds=config.timeout_seconds) as response:
                return MinerUResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            suffix = f": {detail[:500]}" if detail else f": {exc.reason}"
            raise ExternalServiceError(f"MinerU service returned HTTP {exc.code}{suffix}") from exc
        except (error.URLError, http.client.HTTPException, TimeoutError, socket.timeout, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ExternalServiceError(f"MinerU service is unavailable: {reason}") from exc


def _source_output_dir(output_dir: Path, input_path: Path, input_root: Path | None) -> Path:
    if input_root is None:
        return output_dir
    root = input_root.expanduser().resolve()
    try:
        relative_parent = input_path.relative_to(root).parent
    except ValueError as exc:
        raise SourceNotFound(f"Document input file is outside the selected input folder: {input_path}") from exc
    return output_dir / relative_parent


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
    parsed = urlsplit(config.endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DocumentPreprocessorUnavailable("document_processing.mineru.endpoint must be an absolute HTTP(S) URL.")


def _multipart_body(boundary: str, fields: dict[str, object], *, file_field: str, path: Path) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        for item in _multipart_field_values(value):
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    item.encode("utf-8"),
                    b"\r\n",
                ]
            )
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'.encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def _urlopen(req: request.Request, *, timeout_seconds: float):
    hostname = (urlsplit(req.full_url).hostname or "").lower()
    bypass_proxy = hostname == "localhost" or hostname.endswith(".localhost")
    if not bypass_proxy:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            bypass_proxy = address.is_loopback or address.is_private or address.is_link_local
    if bypass_proxy:
        opener = request.build_opener(request.ProxyHandler({}))
        return opener.open(req, timeout=timeout_seconds)
    return request.urlopen(req, timeout=timeout_seconds)  # noqa: S310 - user-configured service adapter


def _multipart_field_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_multipart_scalar(item) for item in value]
    return [_multipart_scalar(value)]


def _multipart_scalar(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _materialize_markdown(
    input_path: Path,
    output_dir: Path,
    response: MinerUResponse,
    config: MinerUDocumentProcessingConfig,
) -> Path | None:
    if _is_zip_response(response):
        return _extract_zip_markdown(input_path, output_dir, response)

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


def _is_zip_response(response: MinerUResponse) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return "zip" in content_type or response.body.startswith(b"PK\x03\x04")


def _extract_zip_markdown(input_path: Path, output_dir: Path, response: MinerUResponse) -> Path | None:
    extracted: list[Path] = []
    destinations: set[Path] = set()
    total_size = 0
    try:
        with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
            for info in archive.infolist():
                member = PurePosixPath(info.filename.replace("\\", "/"))
                if member.is_absolute() or ".." in member.parts:
                    raise ExternalServiceError(f"MinerU ZIP contains an unsafe path: {info.filename}")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ExternalServiceError(f"MinerU ZIP contains an unsupported symbolic link: {info.filename}")
                if info.is_dir():
                    continue
                total_size += info.file_size
                if total_size > 1024 * 1024 * 1024:
                    raise ExternalServiceError("MinerU ZIP exceeds the 1 GiB extracted-size limit.")
                destination = (output_dir / Path(*member.parts)).resolve()
                if destination in destinations or output_dir.resolve() not in destination.parents:
                    raise ExternalServiceError(f"MinerU ZIP contains an invalid or duplicate path: {info.filename}")
                destinations.add(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                extracted.append(destination)
    except zipfile.BadZipFile as exc:
        raise ExternalServiceError("MinerU service returned an invalid ZIP response.") from exc

    markdown = [path for path in extracted if path.suffix.lower() in {".md", ".markdown"}]
    preferred = [path for path in markdown if path.stem == input_path.stem]
    candidates = preferred or markdown
    return min(candidates, key=lambda path: (len(path.parts), str(path))) if candidates else None


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
    assets_root = _raw_derived_assets_root_for_output_dir(output_dir)
    link_rewrites: dict[str, str] = {}
    link_rewrites.update(_materialize_payload_images(input_path, markdown_path, response, assets_root))
    output_attachments, output_rewrites = _output_directory_image_attachments(input_path, markdown_path, output_dir, assets_root)
    link_rewrites.update(output_rewrites)
    if link_rewrites:
        _rewrite_markdown_image_links(markdown_path, link_rewrites)

    attachments: list[dict[str, object]] = []
    attachments.extend(_payload_image_attachments(markdown_path, response, assets_root))
    attachments.extend(discover_markdown_image_attachments(markdown_path, base_dir=assets_root))
    attachments.extend(output_attachments)
    return _enrich_materialized_attachments(dedupe_attachments(attachments), response)


def _output_directory_image_attachments(
    input_path: Path,
    markdown_path: Path,
    output_dir: Path,
    assets_root: Path,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    candidate_dirs = [
        markdown_path.parent / "images",
        markdown_path.parent / input_path.stem / "images",
        output_dir / input_path.stem / "images",
        output_dir / input_path.stem / "auto" / "images",
        output_dir / input_path.stem / "hybrid_auto" / "images",
        output_dir / input_path.stem / "vlm" / "images",
        output_dir / input_path.stem / "hybrid-engine" / "images",
        output_dir / input_path.stem / "vlm-engine" / "images",
    ]
    attachments: list[dict[str, object]] = []
    rewrites: dict[str, str] = {}
    for directory in candidate_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for image_path in sorted(path for path in directory.rglob("*") if path.is_file()):
            asset_path = _copy_to_raw_derived_assets(input_path, image_path, assets_root)
            rewrites[image_path.name] = _markdown_link_to_asset(markdown_path, asset_path)
            try:
                rewrites[image_path.relative_to(markdown_path.parent).as_posix()] = _markdown_link_to_asset(markdown_path, asset_path)
            except ValueError:
                pass
            attachments.append(
                normalize_attachment(
                    asset_path,
                    base_dir=assets_root,
                    name=asset_path.name,
                    source="mineru",
                )
            )
    return attachments, rewrites


def _materialize_payload_images(input_path: Path, markdown_path: Path, response: MinerUResponse, assets_root: Path) -> dict[str, str]:
    payload = _json_payload(response)
    if payload is None:
        return {}
    results = payload.get("results")
    if not isinstance(results, dict):
        return {}
    rewrites: dict[str, str] = {}
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
            image_path = _raw_derived_asset_image_path(input_path, name, image_bytes, assets_root)
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)
            rewrites[name] = _markdown_link_to_asset(markdown_path, image_path)
            rewrites[f"images/{name}"] = _markdown_link_to_asset(markdown_path, image_path)
    return rewrites


def _decode_image_payload(value: str) -> bytes | None:
    data = value.strip()
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _payload_image_attachments(markdown_path: Path, response: MinerUResponse, assets_root: Path) -> list[dict[str, object]]:
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
                base_dir=assets_root,
                name=str(item.get("name") or image_path.name),
                description=_payload_image_description(item),
                source="mineru",
                metadata={key: value for key, value in item.items() if key not in {"path", "image_path", "img_path", "url", "src"}},
            )
        )
    return attachments


def _raw_derived_assets_root_for_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name == "raw":
            return candidate / "derived" / "assets"
    return resolved.parent / "assets"


def _raw_derived_asset_image_path(input_path: Path, name: str, image_bytes: bytes, assets_root: Path) -> Path:
    suffix = Path(name).suffix.lower() or ".png"
    stem = _safe_asset_stem(input_path.stem)
    name_stem = _safe_asset_stem(Path(name).stem)
    digest = hashlib.sha256(image_bytes).hexdigest()[:12]
    return (assets_root / "images" / f"{stem}-{name_stem}-{digest}{suffix}").resolve()


def _copy_to_raw_derived_assets(input_path: Path, image_path: Path, assets_root: Path) -> Path:
    data = image_path.read_bytes()
    target = _raw_derived_asset_image_path(input_path, image_path.name, data, assets_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(image_path, target)
    return target


def _safe_asset_stem(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:48].rstrip(" .-") or "asset"


def _markdown_link_to_asset(markdown_path: Path, asset_path: Path) -> str:
    return Path(os.path.relpath(asset_path, markdown_path.parent)).as_posix()


def _rewrite_markdown_image_links(markdown_path: Path, rewrites: dict[str, str]) -> None:
    content = markdown_path.read_text(encoding="utf-8")
    for old_target, new_target in sorted(rewrites.items(), key=lambda item: len(item[0]), reverse=True):
        content = content.replace(f"]({old_target})", f"]({new_target})")
        content = content.replace(f"]({old_target.replace(' ', '%20')})", f"]({new_target})")
    markdown_path.write_text(content, encoding="utf-8")


def _payload_image_description(item: dict[str, object]) -> str:
    for key in ("caption", "description", "alt", "image_caption", "table_caption"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts = [part.strip() for part in value if isinstance(part, str) and part.strip()]
            if parts:
                return " ".join(parts)
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        return _clean_attachment_content(content)
    table_body = item.get("table_body")
    if isinstance(table_body, str) and table_body.strip():
        return _clean_attachment_content(table_body)
    return ""


def _payload_image_details_by_name(response: MinerUResponse) -> dict[str, dict[str, object]]:
    payload = _json_payload(response)
    if payload is None:
        return {}
    details: dict[str, dict[str, object]] = {}
    for item in _iter_payload_image_items(payload):
        path_value = _payload_path_value(item)
        if not path_value:
            continue
        name = Path(path_value).name
        description = _payload_image_description(item)
        metadata = {key: value for key, value in item.items() if key not in {"path", "image_path", "img_path", "url", "src"}}
        details[name] = {"description": description, "metadata": metadata}
    return details


def _enrich_materialized_attachments(
    attachments: list[dict[str, object]],
    response: MinerUResponse,
) -> list[dict[str, object]]:
    details = _payload_image_details_by_name(response)
    if not details:
        return attachments
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_name = str(attachment.get("name") or "")
        for original_name, detail in details.items():
            original_stem = _safe_asset_stem(Path(original_name).stem)
            if original_stem and original_stem not in _safe_asset_stem(attachment_name):
                continue
            description = detail.get("description")
            if isinstance(description, str) and description.strip():
                attachment["description"] = description.strip()
            metadata = detail.get("metadata")
            if isinstance(metadata, dict) and metadata:
                existing = attachment.get("metadata")
                merged = dict(existing) if isinstance(existing, dict) else {}
                merged.update(metadata)
                attachment["metadata"] = merged
            if str(attachment.get("source") or "").startswith("mineru_") or attachment.get("source") == "markdown_image_link":
                attachment["source"] = "mineru"
            break
    return attachments


def _clean_attachment_content(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if normalized.count("```") == 2:
        fenced = re.fullmatch(r"```([A-Za-z0-9_+-]*)[ \t]*(?:\n|[ \t]+)(.*?)\s*```", normalized, flags=re.DOTALL)
        if fenced:
            language, body = fenced.groups()
            return f"```{language}\n{body.strip()}\n```"
    if "```" in normalized:
        return normalized
    return " ".join(normalized.split())


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


def mineru_health_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    return urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))


def probe_mineru_endpoint(endpoint: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 2.0) -> tuple[bool, str]:
    payload, detail = _mineru_health_payload(endpoint, headers=headers, timeout_seconds=timeout_seconds)
    if payload is None:
        return False, detail
    version = payload.get("protocol_version") or payload.get("version")
    return True, f"health ready{f' ({version})' if version else ''}"


def mineru_max_concurrent_requests(
    endpoint: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 2.0,
) -> int:
    """Return the service-advertised request capacity or the safe fallback."""

    payload, _ = _mineru_health_payload(endpoint, headers=headers, timeout_seconds=timeout_seconds)
    value = payload.get("max_concurrent_requests") if payload is not None else None
    if isinstance(value, bool):
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _mineru_health_payload(
    endpoint: str,
    *,
    headers: dict[str, str] | None,
    timeout_seconds: float,
) -> tuple[dict[str, object] | None, str]:
    health_endpoint = mineru_health_endpoint(endpoint)
    req = request.Request(health_endpoint, headers={"Accept": "application/json", **(headers or {})}, method="GET")
    try:
        with _urlopen(req, timeout_seconds=timeout_seconds) as response:
            body = response.read()
            if response.status < 200 or response.status >= 300:
                return None, f"health HTTP {response.status}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None, "health response is not valid JSON"
            if not isinstance(payload, dict):
                return None, "health response is not a JSON object"
            return payload, "health ready"
    except (error.HTTPError, error.URLError, TimeoutError, socket.timeout, ValueError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return None, f"health unavailable: {reason}"
