from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GeneratedImage(BaseModel):
    url: str | None = None
    b64_json: str | None = None
    mime_type: str = "image/png"
    revised_prompt: str | None = None

    def markdown_src(self) -> str | None:
        if self.url:
            return self.url
        if self.b64_json:
            return f"data:{self.mime_type};base64,{self.b64_json}"
        return None


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    negative_prompt: str | None = None
    resolution: str | None = None
    num_inference_steps: int | None = Field(default=None, ge=1)
    guidance: float | None = Field(default=None, ge=0)
    response_format: Literal["url", "b64_json"] | None = None
    extra_body: dict[str, object] = Field(default_factory=dict)


class ImageGenerationResponse(BaseModel):
    schema_version: Literal["image_generation_response.v1"] = "image_generation_response.v1"
    provider: str
    model: str
    prompt: str
    images: list[GeneratedImage] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    raw: dict[str, object] = Field(default_factory=dict)


class ImageProviderSummary(BaseModel):
    name: str
    adapter: str
    base_url: str | None = None
    model: str | None = None
    default: bool = False
    resolution: str | None = None
    num_inference_steps: int | None = None
    guidance: float | None = None


class ImageProvidersResponse(BaseModel):
    schema_version: Literal["image_providers.v1"] = "image_providers.v1"
    default_provider: str | None = None
    providers: list[ImageProviderSummary] = Field(default_factory=list)
