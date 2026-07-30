from __future__ import annotations

from typing import Any

from knoarbor.core.errors import ExternalServiceError, UserInputError
from knoarbor.core.schemas.chat import ChatToolTraceItem
from knoarbor.core.schemas.image_generation import ImageGenerationRequest
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.services.chat_generated_images import store_chat_generated_image
from knoarbor.services.vault_asset_urls import vault_asset_src

def list_vaults(context: ChatToolContext, arguments: dict[str, Any]) -> ChatToolTraceItem:
    response = context.services.vaults.list_vaults(config_path=str(arguments.get("config_path") or context.request.config_path or "").strip() or None)
    vaults = [vault.model_dump() for vault in response.vaults]
    return ChatToolTraceItem(
        tool="list_vaults",
        arguments=arguments,
        summary=f"Listed {len(vaults)} configured vault(s).",
        result={
            "schema_version": response.schema_version,
            "config_path": response.config_path,
            "default_vault_id": response.default_vault_id,
            "vaults": vaults,
        },
    )


def generate_image(context: ChatToolContext, arguments: dict[str, Any]) -> ChatToolTraceItem:
    prompt = _required_text(arguments, "prompt")
    provider = _optional_text(arguments, "provider")
    request = ImageGenerationRequest(
        prompt=prompt,
        negative_prompt=_optional_text(arguments, "negative_prompt"),
        response_format=arguments.get("response_format") if arguments.get("response_format") in {"url", "b64_json"} else None,
        extra_body=arguments.get("extra_body") if isinstance(arguments.get("extra_body"), dict) else {},
    )
    response = context.services.image_generation.generate(request, config_path=context.request.config_path, provider_name=provider)
    images: list[dict[str, object]] = []
    for index, image in enumerate(response.images, start=1):
        stored = store_chat_generated_image(
            image,
            vault_path=context.request.vault_path,
            session_id=context.request.session_id,
            request_id=context.request.request_id,
            index=index,
            provider=response.provider,
            model=response.model,
            prompt=response.prompt,
            revised_prompt=image.revised_prompt,
        )
        if stored is None or not context.request.vault_path:
            raise ExternalServiceError("Generated image could not be persisted in the active vault.")
        display_src = vault_asset_src(stored.src, context.request.vault_path)
        images.append(
            {
                "index": index,
                "src": display_src,
                "markdown": f"![Generated image {index}]({display_src})",
                "mime_type": stored.mime_type,
                "revised_prompt": image.revised_prompt,
                "stored_path": stored.path,
                "manifest_path": stored.manifest_path,
            }
        )
    return ChatToolTraceItem(
        tool="generate_image",
        arguments=arguments,
        summary=f"Generated {len(images)} image(s) with {response.provider}/{response.model}.",
        result={
            "schema_version": response.schema_version,
            "provider": response.provider,
            "model": response.model,
            "prompt": response.prompt,
            "images": images,
            "usage": response.usage,
        },
    )


def _required_text(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise UserInputError(f"Chat tool argument is required: {key}")
    return value


def _optional_text(arguments: dict[str, Any], key: str) -> str | None:
    value = str(arguments.get(key) or "").strip()
    return value or None
