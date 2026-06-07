from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from knoarbor.core.config import default_config_path, load_config
from knoarbor.runtime.endpoint import runtime_endpoint_path, user_runtime_endpoint_path


class RuntimeContextResponse(BaseModel):
    schema_version: str = "runtime_context.v1"
    service_online: bool = True
    base_url: str
    config_path: str | None = None
    vault_path: str | None = None
    endpoint_path: str | None = None
    user_endpoint_path: str | None = None
    errors: list[str] = Field(default_factory=list)


def create_runtime_router() -> APIRouter:
    router = APIRouter()

    @router.get("/runtime", response_model=RuntimeContextResponse, tags=["runtime"])
    async def runtime_context(request: Request) -> RuntimeContextResponse:
        base_url = str(request.base_url).rstrip("/")
        errors: list[str] = []
        config_path: str | None = None
        vault_path: str | None = None
        endpoint_path: str | None = None

        try:
            resolved_config_path = default_config_path()
            config_path = str(resolved_config_path)
            endpoint_path = str(runtime_endpoint_path(resolved_config_path))
            user_endpoint_path = str(user_runtime_endpoint_path())
            config = load_config(resolved_config_path)
            vault_path = str(config.vault.path)
        except Exception as exc:  # pragma: no cover - defensive runtime disclosure
            errors.append(str(exc))

        return RuntimeContextResponse(
            base_url=base_url,
            config_path=config_path,
            vault_path=vault_path,
            endpoint_path=endpoint_path,
            user_endpoint_path=user_endpoint_path,
            errors=errors,
        )

    return router
