from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from knoarbor.core.errors import ErrorCategory, ErrorCode, KnoArborError, error_hint, error_info
from knoarbor.runtime.logging import runtime_logger


logger = runtime_logger(__name__)


def _json_safe(value: object) -> object:
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="replace")
    return value


def error_payload(exc: BaseException) -> tuple[int, dict[str, object]]:
    info = error_info(exc)
    http_status = int(info.pop("http_status"))
    return http_status, {
        "error": info,
        "detail": info["message"],
    }


def explicit_error_payload(
    *,
    code: ErrorCode,
    category: ErrorCategory,
    message: str,
    http_status: int,
    retryable: bool = False,
    details: object | None = None,
) -> tuple[int, dict[str, object]]:
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "category": category,
            "message": message,
            "retryable": retryable,
            "hint": error_hint(code),
        },
        "detail": message,
    }
    if details is not None:
        payload["error"]["details"] = _json_safe(details)  # type: ignore[index]
    return http_status, payload


async def knoarbor_error_handler(_: Request, exc: KnoArborError) -> JSONResponse:
    status, payload = error_payload(exc)
    return JSONResponse(status_code=status, content=payload)


async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    status, payload = error_payload(exc)
    return JSONResponse(status_code=status, content=payload)


async def file_not_found_handler(_: Request, exc: FileNotFoundError) -> JSONResponse:
    status, payload = error_payload(exc)
    return JSONResponse(status_code=status, content=payload)


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = str(exc.detail) if exc.detail else "HTTP request failed"
    retryable = exc.status_code >= 500
    code: ErrorCode = "KA-INTERNAL-001" if retryable else "KA-INPUT-001"
    category: ErrorCategory = "internal_error" if retryable else "user_input_error"
    _, payload = explicit_error_payload(
        code=code,
        category=category,
        message=message,
        http_status=exc.status_code,
        retryable=retryable,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=exc.headers,
    )


async def request_validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    status, payload = explicit_error_payload(
        code="KA-INPUT-001",
        category="user_input_error",
        message="Request validation failed.",
        http_status=422,
        details=exc.errors(),
    )
    return JSONResponse(status_code=status, content=payload)


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_api_exception path=%s method=%s error=%s", request.url.path, request.method, exc)
    status, payload = explicit_error_payload(
        code="KA-INTERNAL-001",
        category="internal_error",
        message="Unexpected internal error.",
        http_status=500,
        retryable=False,
        details={"error_type": type(exc).__name__},
    )
    return JSONResponse(status_code=status, content=payload)
