"""Small deterministic built-in tools for exercising the registry contract."""

from pydantic import BaseModel, ConfigDict, Field

from mrhub.tools.registry import ToolDefinition, ToolRegistry


class EchoToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)


class EchoToolOutput(BaseModel):
    text: str
    character_count: int = Field(ge=1, le=500)


def _echo(payload: BaseModel) -> EchoToolOutput:
    value = EchoToolInput.model_validate(payload)
    return EchoToolOutput(text=value.text, character_count=len(value.text))


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="text.echo",
            description="Return the supplied text unchanged; performs no external action.",
            input_model=EchoToolInput,
            output_model=EchoToolOutput,
            handler=_echo,
        )
    )
    return registry
