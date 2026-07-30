from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ErrorCategory = Literal[
    "user_input_error",
    "external_service_error",
    "model_output_error",
    "policy_rejection",
    "storage_conflict",
    "internal_error",
]

ErrorCode = Literal[
    "KA-INPUT-001",
    "KA-INPUT-002",
    "KA-CFG-001",
    "KA-CFG-002",
    "KA-VAULT-001",
    "KA-SRC-001",
    "KA-SRC-002",
    "KA-DOC-001",
    "KA-EXT-001",
    "KA-MODEL-001",
    "KA-SEM-001",
    "KA-POLICY-001",
    "KA-STORAGE-001",
    "KA-RUN-001",
    "KA-RUNTIME-001",
    "KA-INTERNAL-001",
]


@dataclass(frozen=True)
class ErrorDescriptor:
    code: ErrorCode
    category: ErrorCategory
    message: str
    http_status: int
    retryable: bool = False


ERROR_HINTS: dict[ErrorCode, str] = {
    "KA-INPUT-001": "Check the command arguments or request payload and retry.",
    "KA-INPUT-002": "Check that the file path exists and is readable from the current runtime environment.",
    "KA-CFG-001": "Create config.yaml from config.example.yaml or pass --config with a valid path.",
    "KA-CFG-002": "Fix config.yaml according to config.example.yaml and run `kno doctor` again.",
    "KA-VAULT-001": "Check the vault path and initialize it with `kno init` if needed.",
    "KA-SRC-001": "Check connector settings in config.yaml, including enabled flags and source paths.",
    "KA-SRC-002": "Check that the configured source path exists and is readable.",
    "KA-DOC-001": "Configure a document preprocessor such as MinerU, or provide Markdown input directly.",
    "KA-EXT-001": "Check the external service endpoint, credentials, and network connectivity; this error is retryable.",
    "KA-MODEL-001": "Check model provider output, JSON mode support, max tokens, and retry with a smaller input if needed.",
    "KA-SEM-001": "The model output violated a semantic contract; retry or reduce the source segment size.",
    "KA-POLICY-001": "Review the policy decision and adjust the input or configuration if the rejection is expected.",
    "KA-STORAGE-001": "Another process may be writing the vault; wait for it to finish and retry.",
    "KA-RUN-001": "Check the run id and vault path, then refresh the run list.",
    "KA-RUNTIME-001": "Check the local runtime environment and installed optional dependencies.",
    "KA-INTERNAL-001": "Open an issue with the command, report, and logs if this repeats.",
}


class KnoArborError(ValueError):
    """Base class for structured application errors."""

    code: ErrorCode = "KA-INTERNAL-001"
    category: ErrorCategory = "internal_error"
    http_status: int = 500
    retryable: bool = False

    def descriptor(self) -> ErrorDescriptor:
        return ErrorDescriptor(
            code=self.code,
            category=self.category,
            message=str(self),
            http_status=self.http_status,
            retryable=self.retryable,
        )


class UserInputError(KnoArborError):
    code: ErrorCode = "KA-INPUT-001"
    category: ErrorCategory = "user_input_error"
    http_status = 400


class InputFileNotFound(UserInputError):
    code: ErrorCode = "KA-INPUT-002"


class WikiPageNotFound(InputFileNotFound):
    http_status = 404


class ConfigNotFound(UserInputError):
    code: ErrorCode = "KA-CFG-001"


class InvalidConfig(UserInputError):
    code: ErrorCode = "KA-CFG-002"


class VaultPathError(UserInputError):
    code: ErrorCode = "KA-VAULT-001"


class ConnectorConfigError(UserInputError):
    code: ErrorCode = "KA-SRC-001"


class SourceNotFound(UserInputError):
    code: ErrorCode = "KA-SRC-002"


class DocumentPreprocessorUnavailable(UserInputError):
    code: ErrorCode = "KA-DOC-001"


class ExternalServiceError(KnoArborError):
    code: ErrorCode = "KA-EXT-001"
    category: ErrorCategory = "external_service_error"
    http_status = 502
    retryable = True


class ModelOutputError(KnoArborError):
    code: ErrorCode = "KA-MODEL-001"
    category: ErrorCategory = "model_output_error"
    http_status = 502
    retryable = True


class SemanticContractError(ModelOutputError):
    code: ErrorCode = "KA-SEM-001"


class PolicyRejection(KnoArborError):
    code: ErrorCode = "KA-POLICY-001"
    category: ErrorCategory = "policy_rejection"
    http_status = 422


class StorageConflict(KnoArborError):
    code: ErrorCode = "KA-STORAGE-001"
    category: ErrorCategory = "storage_conflict"
    http_status = 409
    retryable = True


class MaterializationPending(StorageConflict):
    """The requested knowledge view may appear after materialization completes."""


class InternalKnoArborError(KnoArborError):
    code: ErrorCode = "KA-INTERNAL-001"
    category: ErrorCategory = "internal_error"
    http_status = 500


class RunNotFound(UserInputError):
    code: ErrorCode = "KA-RUN-001"


class RuntimeCapabilityError(InternalKnoArborError):
    code: ErrorCode = "KA-RUNTIME-001"


def describe_exception(exc: BaseException) -> ErrorDescriptor:
    """Map known exception families into the public error taxonomy."""
    if isinstance(exc, KnoArborError):
        return exc.descriptor()
    if isinstance(exc, FileNotFoundError):
        return ErrorDescriptor(
            code="KA-INPUT-002",
            category="user_input_error",
            message=str(exc),
            http_status=400,
        )
    if isinstance(exc, ValueError):
        return ErrorDescriptor(
            code="KA-INPUT-001",
            category="user_input_error",
            message=str(exc),
            http_status=400,
        )
    return ErrorDescriptor(
        code="KA-INTERNAL-001",
        category="internal_error",
        message=str(exc),
        http_status=500,
    )


def error_hint(code: ErrorCode) -> str:
    """Return a stable user-facing remediation hint for an error code."""
    return ERROR_HINTS[code]


def error_info(exc: BaseException) -> dict[str, object]:
    """Serialize an exception into the public error contract."""
    descriptor = describe_exception(exc)
    return {
        "code": descriptor.code,
        "category": descriptor.category,
        "message": descriptor.message,
        "http_status": descriptor.http_status,
        "retryable": descriptor.retryable,
        "hint": error_hint(descriptor.code),
        "error_type": type(exc).__name__,
    }
