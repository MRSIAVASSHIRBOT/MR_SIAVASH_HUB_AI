"""Explicit, in-memory registry for video-generation adapters."""

from __future__ import annotations

from mrhub.video_intelligence.generation import (
    VideoGenerationCapability,
    VideoGenerationProvider,
)


class VideoGenerationRegistry:
    """Only explicitly registered adapters are visible or selectable."""

    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], VideoGenerationProvider] = {}

    def register(self, provider: VideoGenerationProvider) -> None:
        capability = provider.capability
        key = (capability.provider, capability.model)
        if key in self._providers:
            raise ValueError("Video generation provider is already registered")
        self._providers[key] = provider

    def get(self, provider: str, model: str) -> VideoGenerationProvider:
        try:
            return self._providers[(provider, model)]
        except KeyError as exc:
            raise LookupError("No video generation adapter is configured for this model") from exc

    def catalog(self) -> list[VideoGenerationCapability]:
        return [self._providers[key].capability for key in sorted(self._providers)]


# Adapters are registered by explicit application configuration only.
video_generation_registry = VideoGenerationRegistry()
