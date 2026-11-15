"""Explicit, in-memory registry for video-generation adapters."""
from __future__ import annotations

from mrhub.video_intelligence.generation import (
    VideoGenerationCapability,
    VideoGenerationProvider,
)


class VideoGenerationRegistry:
    """Only explicitly registered, contract-complete adapters are selectable."""

    REQUIRED_METHODS = (
        "submit",
        "get_status",
        "find_by_idempotency_key",
        "download_output",
        "cancel",
    )

    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], VideoGenerationProvider] = {}

    def register(self, provider: VideoGenerationProvider) -> None:
        capability = getattr(provider, "capability", None)
        if not isinstance(capability, VideoGenerationCapability):
            raise TypeError(
                "Video generation provider must expose a valid VideoGenerationCapability"
            )

        missing = [
            name
            for name in self.REQUIRED_METHODS
            if not callable(getattr(provider, name, None))
        ]
        if missing:
            raise TypeError(
                "Video generation provider is missing required methods: "
                + ", ".join(missing)
            )

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
        return [
            self._providers[key].capability
            for key in sorted(self._providers)
        ]


# Adapters are registered by explicit application configuration only.
video_generation_registry = VideoGenerationRegistry()
