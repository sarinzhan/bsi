"""chat module: chats, messages and the live event stream (in the web app's AgentEvent format)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from platform_api.access.schemas import AccessCheck
from platform_api.agent.schemas import Runs
from platform_api.chat.repositories.memory import InMemoryChatRepository
from platform_api.chat.service import ChatService
from platform_api.chat.schemas import ChatEventSink, Chats, RunnerChat
from platform_api.chat.interfaces import ChatRepository

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class ChatModule:
    chats: Chats  # web app
    events: ChatEventSink  # approval module, wiring
    runner: RunnerChat  # agent containers, wiring (run ended)


def create_chat_module(runs: Runs, access: AccessCheck, engine: "Engine | None" = None) -> ChatModule:
    repo: ChatRepository
    if engine is None:
        repo = InMemoryChatRepository()
    else:
        from platform_api.chat.repositories.postgres import PostgresChatRepository

        repo = PostgresChatRepository(engine)
    service = ChatService(repo, runs, access)
    return ChatModule(chats=service, events=service, runner=service)
