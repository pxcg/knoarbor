from __future__ import annotations

from pathlib import Path
from time import perf_counter

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import KnoArborError, UserInputError, describe_exception
from knoarbor.core.schemas.image_generation import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    ImageProviderProbeRequest,
    ImageProviderProbeResponse,
    ImageProviderSummary,
    ImageProvidersResponse,
)
from knoarbor.semantic.image_generation import ImageGenerationGateway


class ImageGenerationService:
    """Owns image generation provider selection and runtime invocation."""

    def is_available(self, config_path: str | None = None) -> bool:
        """Return whether the configured default provider can be constructed."""

        try:
            config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
            selected = config.image_generation.default_provider
            provider = config.image_generation.providers.get(selected) if selected else None
            if not selected or provider is None:
                return False
            ImageGenerationGateway.from_config(
                selected,
                provider,
                timeout_seconds=config.image_generation.request_timeout_seconds,
            )
        except (KnoArborError, ValueError, OSError):
            return False
        return True

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

    def probe(self, request: ImageProviderProbeRequest) -> ImageProviderProbeResponse:
        """Run an explicit, real image-generation smoke test.

        Image endpoints do not share a reliable metadata operation, so this
        probe is intentionally separate from text-model discovery and only
        runs when the user explicitly requests it.
        """

        config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
        selected = request.provider or config.image_generation.default_provider
        if not selected:
            raise UserInputError("No image generation provider selected.")
        provider = config.image_generation.providers.get(selected)
        if provider is None:
            raise UserInputError(f"Unknown image generation provider: {selected}")

        started = perf_counter()
        try:
            response = self.generate(
                ImageGenerationRequest(prompt=request.prompt),
                config_path=request.config_path,
                provider_name=selected,
            )
            usable_images = [image for image in response.images if image.markdown_src()]
            if not usable_images:
                raise ValueError("The provider returned no usable image.")
        except (KnoArborError, ValueError, OSError) as exc:
            descriptor = describe_exception(exc)
            return ImageProviderProbeResponse(
                provider=selected,
                model=provider.model or "",
                adapter=provider.adapter,
                status="error",
                available=False,
                message=str(exc)[:500] or "Image generation test failed.",
                elapsed_ms=max(0, round((perf_counter() - started) * 1000)),
                image_count=0,
                error_code=descriptor.code,
                retryable=descriptor.retryable,
            )

        return ImageProviderProbeResponse(
            provider=selected,
            model=response.model,
            adapter=provider.adapter,
            status="ok",
            available=True,
            message="Image generation completed successfully.",
            elapsed_ms=max(0, round((perf_counter() - started) * 1000)),
            image_count=len(usable_images),
            mime_types=sorted({image.mime_type for image in usable_images}),
        )
