"""A model without a model: a fixed script. Lets the whole chain run (container -> server tools -> approval
card -> SSH -> chat) without an API key or cost. BSI_LLM=scripted.

Turn 1: call docker_ps on BSI_SCRIPTED_SERVER. Turn 2: answer with what came back.
"""

from __future__ import annotations

from typing import Any

from agent_runner.interfaces import Model, Reply, ToolCall, ToolSpec


class ScriptedModel(Model):
    def __init__(self, server: str = "dev-docker-01", tool: str = "docker_ps") -> None:
        self._server, self._tool = server, tool

    async def next(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply:
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):  # the tool result is back
            result = last["content"][0]
            first_line = (result["content"] or "").splitlines()[0:3]
            outcome = "was not allowed" if result["is_error"] else "worked"
            text = f"(scripted) {self._tool} on {self._server} {outcome}: " + " / ".join(first_line)
            return Reply([{"type": "text", "text": text}], "end_turn", text)
        call = ToolCall("toolu_scripted_1", self._tool, {"server": self._server})
        intro = f"(scripted) Checking the containers on {self._server}."
        content = [{"type": "text", "text": intro},
                   {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}]
        return Reply(content, "tool_use", intro, [call])
