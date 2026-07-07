from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.image_generation import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    ImageProviderSummary,
    ImageProvidersResponse,
)
from knoarbor.semantic.image_generation import ImageGenerationGateway


class ImageGenerationService:
    """Owns image generation provider selection and runtime invocation."""

    def providers(self, config_path: str | None = None) -> ImageProvidersResponse:
        config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
        providers = [
            ImageProviderSummary(
                name=name,
                adapter=provider.adapter,
                base_url=provider.base_url,
                model=provider.model,
                default=name == config.image_generation.default_provider,
                resolution=provider.resolution,
                num_inference_steps=provider.num_inference_steps,
                guidance=provider.guidance,
            )
            for name, provider in sorted(config.image_generation.providers.items())
        ]
        return ImageProvidersResponse(default_provider=config.image_generation.default_provider, providers=providers)

    def generate(
        self,
        request: ImageGenerationRequest,
        *,
        config_path: str | None = None,
        provider_name: str | None = None,
    ) -> ImageGenerationResponse:
        config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
        selected = provider_name or config.image_generation.default_provider
        if not selected:
            raise UserInputError("No image generation provider configured.")
        provider = config.image_generation.providers.get(selected)
        if provider is None:
            raise UserInputError(f"Unknown image generation provider: {selected}")
        gateway = ImageGenerationGateway.from_config(
            selected,
            provider,
            timeout_seconds=config.image_generation.request_timeout_seconds,
        )
        return gateway.generate(request)
