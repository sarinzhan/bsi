"""What the agent loop needs: a model, the server tools and platform-api. integrations/ implements these."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    """One model turn. `content` is passed back unchanged on the next turn (it may hold thinking blocks)."""

    content: list[Any]
    stop_reason: str  # end_turn | tool_use | max_tokens | refusal | ...
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class ToolResult:
    text: str
    is_error: bool  # denied, rejected or failed: the model sees why and decides what to do


@dataclass(frozen=True)
class Context:
    chat_id: str
    system: str
    env: str
    messages: list[dict[str, str]]  # [{"role": "user" | "assistant", "text": ...}], oldest first


class ModelUnavailable(RuntimeError):
    """The model could not answer (bad key, rate limit, network). The message is shown in the chat."""


class Model(Protocol):
    async def next(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply: ...


class Tools(Protocol):
    async def list(self) -> list[ToolSpec]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


class Platform(Protocol):
    async def context(self) -> Context: ...

    async def post(self, event: dict[str, Any]) -> None: ...  # AgentEvent: agent messages, steps

    async def finish(self, outcome: str, error: str | None = None) -> None: ...  # finished | failed
