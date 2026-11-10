"""The agent loop: ask the model, run the tools it asks for, give it the results, until it answers.

Every tool call goes through platform-api's tools, which check it, ask a person in the chat and run it.
A denied or rejected call comes back as an error result: the model sees why and carries on.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from agent_runner.interfaces import Model, ModelUnavailable, Platform, Tools

MAX_TURNS = 30
DEADLINE_MARGIN = timedelta(seconds=30)  # stop cleanly before platform-api stops the container


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _history(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The conversation so far, as model messages. It must start with the user."""
    out = [{"role": m["role"], "content": m["text"]} for m in messages if m.get("text")]
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


async def run(model: Model, tools: Tools, platform: Platform, system_prompt: Callable[[str, str, str], str],
              max_turns: int = MAX_TURNS, deadline: datetime | None = None,
              clock: Callable[[], datetime] = _now,
              new_id: Callable[[], str] = lambda: "a_" + secrets.token_hex(6)) -> str:
    """Runs one agent turn for the chat's latest message. Always reports finished or failed. Returns the outcome."""
    try:
        ctx = await platform.context()
        messages = _history(ctx.messages)
        if not messages:
            raise ValueError("nothing to answer: the chat has no user message")
        system = system_prompt(ctx.system, ctx.env, ctx.chat_id)
        specs = await tools.list()
        for _ in range(max_turns):
            if deadline is not None and clock() >= deadline - DEADLINE_MARGIN:
                return await _fail(platform, "the run reached its time limit")
            reply = await model.next(system, messages, specs)
            messages.append({"role": "assistant", "content": reply.content})  # unchanged: may hold thinking
            if reply.stop_reason == "refusal":
                return await _fail(platform, "the model declined this request")
            if reply.stop_reason == "max_tokens":
                return await _fail(platform, "the answer got too long")
            if reply.stop_reason == "pause_turn":
                continue
            if not reply.tool_calls:
                await _say(platform, new_id(), reply.text.strip() or "(no answer)")
                await platform.finish("finished")
                return "finished"
            if reply.text.strip():  # what it is about to do, shown in the chat
                await _say(platform, new_id(), reply.text.strip())
            results = []
            for call in reply.tool_calls:  # all results go back in one message
                result = await tools.call(call.name, call.input)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": result.text or "(no output)", "is_error": result.is_error})
            messages.append({"role": "user", "content": results})
        return await _fail(platform, f"stopped after {max_turns} steps without an answer")
    except ModelUnavailable as e:
        return await _fail(platform, str(e))
    except Exception as e:  # anything else: the chat must still learn the run ended
        return await _fail(platform, f"{type(e).__name__}: {e}"[:300])


async def _say(platform: Platform, message_id: str, text: str) -> None:
    await platform.post({"type": "message", "message": {"id": message_id, "role": "agent", "text": text}})


async def _fail(platform: Platform, why: str) -> str:
    try:
        await platform.finish("failed", why)  # platform-api writes "The agent stopped: <why>" in the chat
    except Exception:
        pass  # platform-api unreachable: the run expires at its deadline anyway
    return "failed"
