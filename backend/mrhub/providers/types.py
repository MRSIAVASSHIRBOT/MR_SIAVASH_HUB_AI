"""Shared immutable model capability and descriptor types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapability:
    text: bool = True
    vision: bool = False
    audio: bool = False
    tool_calling: bool = False


@dataclass(frozen=True)
class ModelDescriptor:
    provider: str
    model: str
    capability: ModelCapability
    available: bool = True
    local: bool = False
    priority: int = 100
