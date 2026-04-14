from __future__ import annotations

import uuid

from src.megahub_monitor.domain.models import AllocationSuggestion, EnhancedLoadEntry
from src.megahub_monitor.ports.approval_gateway import AllocationApproved, ApprovalGateway


class FakeApprovalGateway(ApprovalGateway):
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._pending_results: dict[str, AllocationApproved | None] = {}

    def send_approval_request(
        self,
        ticket_number: str,
        source_id: str,
        suggestions: list[AllocationSuggestion],
        load_board: list[EnhancedLoadEntry],
        coordinator_webhook_url: str,
    ) -> str:
        request_id = str(uuid.uuid4())
        self.requests.append({
            "request_id": request_id,
            "ticket_number": ticket_number,
            "source_id": source_id,
        })
        return request_id

    def poll_approval(self, request_id: str) -> AllocationApproved | None:
        return self._pending_results.get(request_id)

    def set_approval_result(self, request_id: str, result: AllocationApproved | None) -> None:
        self._pending_results[request_id] = result
