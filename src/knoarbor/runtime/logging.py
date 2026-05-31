from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_runtime_logging(vault_path: Path, *, level: int = logging.INFO) -> Path:
    """Configure process logging for local runtime diagnostics."""

    log_path = logs_dir(vault_path) / "knoarbor.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("knoarbor")
    logger.setLevel(level)
    logger.propagate = False

    _remove_stale_runtime_handlers(logger, log_path)
    if not _has_file_handler(logger, log_path):
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        setattr(handler, "_knoarbor_runtime_log", True)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)

    return log_path


def logs_dir(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "logs"


def runtime_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name == "knoarbor" or name.startswith("knoarbor.") else f"knoarbor.{name}")


def _has_file_handler(logger: logging.Logger, log_path: Path) -> bool:
    wanted = log_path.resolve()
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(handler, "_knoarbor_runtime_log", False):
            try:
                if Path(handler.baseFilename).resolve() == wanted:
                    return True
            except OSError:
                continue
    return False


def _remove_stale_runtime_handlers(logger: logging.Logger, log_path: Path) -> None:
    wanted = log_path.resolve()
    for handler in list(logger.handlers):
        if not isinstance(handler, RotatingFileHandler) or not getattr(handler, "_knoarbor_runtime_log", False):
            continue
        try:
            if Path(handler.baseFilename).resolve() == wanted:
                continue
        except OSError:
            pass
        logger.removeHandler(handler)
        handler.close()
