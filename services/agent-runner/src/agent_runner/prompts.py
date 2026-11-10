"""The system prompt: the agent's instructions from the repo (agent/*.md) plus what this run is about."""

from __future__ import annotations

from pathlib import Path

RUN_NOTES = """\
# This run

System: {system}. Environment: {env}. Chat: {chat}.

What you can do in this version: look at the servers of this system and environment with the server tools,
then explain what you found. You cannot change code, open merge requests or use report_* tools yet, even if
the instructions above mention them. Answer in plain words, short, and quote only the log lines that matter.
"""

FALLBACK = "You are the engineering agent of BSI. Use the server tools to look at the servers, then explain."


def load(prompts_dir: Path):
    """Returns system_prompt(system, env, chat) -> str. Reads the files once, at start."""
    parts = []
    for name, title in (("system-prompt.md", None), ("server-tools.md", "# Server tools reference")):
        path = prompts_dir / name
        if path.exists():
            text = path.read_text()
            parts.append(f"{title}\n\n{text}" if title else text)
    base = "\n\n".join(parts) or FALLBACK

    def system_prompt(system: str, env: str, chat: str) -> str:
        return f"{base}\n\n{RUN_NOTES.format(system=system, env=env, chat=chat)}"

    return system_prompt
