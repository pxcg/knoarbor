from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from knoarbor.product import product_env, product_env_name
from knoarbor.runtime.locks import FileLock


PROVIDER_CONTROL_SCHEMA = "provider_admission.v1"
RUNTIME_DIR_ENV = product_env_name("RUNTIME_DIR")
CONFIG_PATH_ENV = product_env_name("CONFIG_PATH")


def provider_control_path() -> Path:
    runtime_dir = product_env("RUNTIME_DIR")
    if runtime_dir:
        root = Path(runtime_dir).expanduser().resolve()
    else:
        config_path = Path(product_env("CONFIG_PATH") or Path.cwd() / "config.yaml").expanduser().resolve()
        root = config_path.parent / "state"
    return root / "provider_admission.json"


def provider_cooldown_until(provider_key: str) -> float:
    return _deadline(_read().get("cooldowns", {}).get(provider_key))


def impose_provider_cooldown(provider_key: str, *, seconds: float) -> float:
    deadline = time.time() + max(0.0, seconds)
    path = provider_control_path()
    with FileLock(path.with_suffix(".lock")):
        state = _read(path)
        cooldowns = dict(state["cooldowns"])
        cooldowns[provider_key] = max(_deadline(cooldowns.get(provider_key)), deadline)
        state["cooldowns"] = cooldowns
        _write(path, state)
    return deadline


def wait_for_provider_admission(
    provider_key: str,
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
    on_wait: Callable[[str, float], None] | None = None,
    poll_seconds: float = 0.2,
) -> None:
    while True:
        if raise_if_cancelled:
            raise_if_cancelled()
        remaining = max(0.0, provider_cooldown_until(provider_key) - time.time())
        if remaining <= 0:
            return
        if on_wait:
            on_wait("rate_limited", remaining)
        time.sleep(min(poll_seconds, remaining))


def _read(path: Path | None = None) -> dict[str, object]:
    path = path or provider_control_path()
    default: dict[str, object] = {"schema_version": PROVIDER_CONTROL_SCHEMA, "cooldowns": {}}
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    if not isinstance(payload, dict):
        return default
    cooldowns = payload.get("cooldowns")
    return {"schema_version": PROVIDER_CONTROL_SCHEMA, "cooldowns": cooldowns if isinstance(cooldowns, dict) else {}}


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _deadline(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
