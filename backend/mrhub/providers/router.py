"""Model routing abstractions with no implicit network access."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


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


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False


class ModelSelection(BaseModel):
    provider: str
    model: str
    local: bool
    rationale: str


class ModelProvider(Protocol):
    descriptor: ModelDescriptor


class ModelRouter:
    """Selects from explicitly registered descriptors; it does not call providers."""

    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], ModelDescriptor] = {}

    def register(self, descriptor: ModelDescriptor) -> None:
        key = (descriptor.provider, descriptor.model)
        self._providers[key] = descriptor

    def catalog(self) -> list[ModelDescriptor]:
        return sorted(
            (item for item in self._providers.values() if item.available),
            key=lambda item: (not item.local, item.priority, item.provider, item.model),
        )

    def select(self, request: ModelRequest) -> ModelSelection:
        candidates = [item for item in self._providers.values() if item.available]
        if request.requires_vision:
            candidates = [item for item in candidates if item.capability.vision]
        if request.requires_audio:
            candidates = [item for item in candidates if item.capability.audio]
        if request.requires_tool_calling:
            candidates = [item for item in candidates if item.capability.tool_calling]
        if request.prefer_local:
            candidates = [item for item in candidates if item.local]
        if not candidates:
            raise LookupError("No available model satisfies the requested capabilities")
        selected = sorted(
            candidates,
            key=lambda item: (not item.local if request.prefer_local else False,
                              item.priority, item.provider, item.model),
        )[0]
        return ModelSelection(
            provider=selected.provider,
            model=selected.model,
            local=selected.local,
            rationale="Selected from registered available models by capability and priority",
        )
