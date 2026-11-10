"""The model: the Claude API (Anthropic Python SDK).

- claude-opus-5-5 by default, adaptive thinking, explicit effort (this model defaults to "medium").
- Streams the request (large max_tokens) and waits for the final message.
- Server-side refusal fallbacks are on ("default"): a declined request is retried on a suitable model.
- Prompt caching on: the system prompt and tool list are the same every turn.
"""

from __future__ import annotations

from typing import Any

import anthropic

from agent_runner.interfaces import Model, ModelUnavailable, Reply, ToolCall, ToolSpec

# Fail fast when the API can not be reached at all (no internet, proxy missing): 15 s to connect instead of
# the SDK's 10 minutes, so the chat says "cannot reach the model API" within a minute instead of hanging.
# Reading stays long: a streamed answer with thinking can take minutes.
TIMEOUT = anthropic.Timeout(600.0, connect=15.0)  # the SDK's own type (it uses httpx2, not httpx)


class AnthropicModel(Model):
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high", max_tokens: int = 64000,
                 client: anthropic.AsyncAnthropic | None = None) -> None:
        self._model, self._effort, self._max_tokens = model, effort, max_tokens
        # ANTHROPIC_API_KEY (and HTTPS_PROXY / NO_PROXY, if set) from the environment
        self._client = client or anthropic.AsyncAnthropic(timeout=TIMEOUT, max_retries=2)

    async def next(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply:
        print(f"asking {self._model} ({len(messages)} messages)", flush=True)  # docker logs bsi-run_...
        try:
            async with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
                tools=[{"name": t.name, "description": t.description, "input_schema": t.input_schema,
                        "eager_input_streaming": True} for t in tools],
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                message = await stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise ModelUnavailable("the Anthropic API key is missing or wrong") from e
        except anthropic.PermissionDeniedError as e:
            raise ModelUnavailable("the Anthropic API key may not use this model") from e
        except anthropic.RateLimitError as e:
            raise ModelUnavailable("the model is rate limited; try again in a minute") from e
        except anthropic.APIStatusError as e:
            raise ModelUnavailable(f"the model API answered {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            print(f"cannot reach the model API: {e!r} (cause: {e.__cause__!r})", flush=True)
            raise ModelUnavailable("cannot reach the model API (no internet or proxy on the server?)") from e
        text = "".join(b.text for b in message.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input if isinstance(b.input, dict) else {})
                 for b in message.content if b.type == "tool_use"]
        return Reply(list(message.content), message.stop_reason or "end_turn", text, calls)
