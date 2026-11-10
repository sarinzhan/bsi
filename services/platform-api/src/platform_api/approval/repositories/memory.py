"""Approvals in memory (tests, quick local runs without a database)."""

from __future__ import annotations

import threading

from platform_api.approval.models import Approval
from platform_api.approval.interfaces import ApprovalRepository


class InMemoryApprovalRepository(ApprovalRepository):
    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}
        self._grants: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def add(self, approval: Approval) -> None:
        with self._lock:
            self._approvals[approval.id] = approval

    def save(self, approval: Approval) -> None:
        with self._lock:
            self._approvals[approval.id] = approval

    def get(self, approval_id: str) -> Approval | None:
        return self._approvals.get(approval_id)

    def has_read_grant(self, chat_id: str, server: str) -> bool:
        return (chat_id, server) in self._grants

    def add_read_grant(self, chat_id: str, server: str, user_id: str) -> None:
        with self._lock:
            self._grants.add((chat_id, server))
