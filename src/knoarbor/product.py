from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


PRODUCT_MANIFEST_SCHEMA = "knoarbor.product.v1"


@dataclass(frozen=True)
class ProductIdentity:
    name: str
    service_title: str
    default_vault_name: str
    env_prefix: str
    desktop_app_data_dir: str
    desktop_app_id: str
    desktop_app_user_model_id: str
    renderer_scheme: str
    renderer_host: str
    renderer_logo_path: str
    help_url: str | None
    show_public_help: bool
    supports_desktop_updates: bool


def load_product_identity() -> ProductIdentity:
    manifest_path = files("knoarbor").joinpath("product_manifest.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(payload)
    product = payload["product"]
    environment = payload["environment"]
    desktop = payload["desktop"]
    renderer = payload["renderer"]
    links = payload["links"]
    capabilities = payload["capabilities"]
    return ProductIdentity(
        name=product["name"],
        service_title=product["service_title"],
        default_vault_name=product["default_vault_name"],
        env_prefix=environment["prefix"],
        desktop_app_data_dir=desktop["app_data_dir"],
        desktop_app_id=desktop["app_id"],
        desktop_app_user_model_id=desktop["app_user_model_id"],
        renderer_scheme=desktop["renderer_scheme"],
        renderer_host=desktop["renderer_host"],
        renderer_logo_path=renderer["logo_path"],
        help_url=links["help"],
        show_public_help=capabilities["public_help"],
        supports_desktop_updates=capabilities["desktop_updates"],
    )


def product_env_name(name: str) -> str:
    normalized = name.strip().upper()
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError(f"Invalid product environment suffix: {name!r}")
    return f"{PRODUCT.env_prefix}_{normalized}"


def product_env(name: str) -> str | None:
    value = os.environ.get(product_env_name(name))
    return value.strip() if value and value.strip() else None


def _validate_manifest(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Product manifest must be an object.")
    expected = {
        "schema_version",
        "product",
        "environment",
        "desktop",
        "renderer",
        "links",
        "capabilities",
    }
    if set(payload) != expected:
        raise ValueError(f"Product manifest fields must be {sorted(expected)}.")
    if payload["schema_version"] != PRODUCT_MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported product manifest schema: {payload['schema_version']!r}.")
    sections = {
        "product": {"name", "service_title", "default_vault_name"},
        "environment": {"prefix"},
        "desktop": {
            "app_data_dir",
            "app_id",
            "app_user_model_id",
            "renderer_host",
            "renderer_scheme",
        },
        "renderer": {"logo_path"},
        "links": {"help"},
        "capabilities": {"desktop_updates", "public_help"},
    }
    for section, fields_expected in sections.items():
        value = payload[section]
        if not isinstance(value, dict) or set(value) != fields_expected:
            raise ValueError(f"Product manifest section {section!r} must contain {sorted(fields_expected)}.")
    for section in ("product", "environment", "desktop", "renderer"):
        for field, value in payload[section].items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Product manifest field {section}.{field} must be a non-empty string.")
    if payload["links"]["help"] is not None and not isinstance(payload["links"]["help"], str):
        raise ValueError("Product manifest field links.help must be a string or null.")
    for field, value in payload["capabilities"].items():
        if not isinstance(value, bool):
            raise ValueError(f"Product manifest field capabilities.{field} must be a boolean.")


PRODUCT = load_product_identity()
