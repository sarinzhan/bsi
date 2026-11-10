"""What the approval module needs."""

from __future__ import annotations

from typing import Protocol

from platform_api.approval.models import Approval


class ApprovalRepository(Protocol):
    def add(self, approval: Approval) -> None: ...

    def save(self, approval: Approval) -> None: ...

    def get(self, approval_id: str) -> Approval | None: ...

    def has_read_grant(self, chat_id: str, server: str) -> bool: ...

    def add_read_grant(self, chat_id: str, server: str, user_id: str) -> None: ...
