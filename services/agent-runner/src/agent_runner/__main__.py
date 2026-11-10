"""Entry point of an agent container: python -m agent_runner

Settings come from platform-api when it starts the container:
  BSI_RUN_TOKEN, BSI_MCP_URL, BSI_PLATFORM_URL, BSI_RUN_DEADLINE,
  BSI_MODEL (default claude-opus-5-5), BSI_EFFORT (default high),
  BSI_LLM = anthropic (default) | scripted (no model, for testing the chain), ANTHROPIC_API_KEY
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from agent_runner import loop, prompts
from agent_runner.integrations import mcp_tools
from agent_runner.integrations.platform_http import PlatformApi
from agent_runner.interfaces import Model

DEFAULT_PROMPTS = Path(__file__).resolve().parents[4] / "agent"  # repo checkout; the image sets BSI_PROMPTS_DIR


def model_from_env() -> Model:
    if os.environ.get("BSI_LLM", "anthropic") == "scripted":
        from agent_runner.integrations.scripted_model import ScriptedModel

        return ScriptedModel(os.environ.get("BSI_SCRIPTED_SERVER", "dev-docker-01"))
    from agent_runner.integrations.anthropic_model import AnthropicModel

    return AnthropicModel(os.environ.get("BSI_MODEL", "claude-opus-5-5"), os.environ.get("BSI_EFFORT", "high"))


async def main() -> int:
    token = os.environ["BSI_RUN_TOKEN"]
    platform = PlatformApi(os.environ["BSI_PLATFORM_URL"], token)
    deadline = os.environ.get("BSI_RUN_DEADLINE")
    system_prompt = prompts.load(Path(os.environ.get("BSI_PROMPTS_DIR", str(DEFAULT_PROMPTS))))
    try:
        model = model_from_env()
        async with mcp_tools.connect(os.environ["BSI_MCP_URL"], token) as tools:
            outcome = await loop.run(model, tools, platform, system_prompt,
                                     deadline=datetime.fromisoformat(deadline) if deadline else None)
    except Exception as e:  # could not even connect to the server tools
        try:
            await platform.finish("failed", f"cannot reach the server tools: {type(e).__name__}")
        except Exception:
            pass  # platform-api unreachable too: the run expires at its deadline
        outcome = "failed"
    print(f"agent run {os.environ.get('BSI_RUN_ID', '?')}: {outcome}", flush=True)
    return 0 if outcome == "finished" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
