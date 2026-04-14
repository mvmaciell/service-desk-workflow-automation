from src.megahub_monitor.domain.enums import (
    AllocationStrategy,
    AuditAction,
    NotificationType,
    TicketWorkflowState,
    can_transition,
)


class TestTicketWorkflowState:
    def test_all_expected_states_exist(self):
        expected = {
            "DETECTED",
            "ALLOCATION_SUGGESTED",
            "ALLOCATION_APPROVED",
            "ASSIGNED",
            "IN_PROGRESS",
            "COMPLETED",
            "COMPLETION_NOTIFIED",
            "FAILED_RETRYABLE",
            "CANCELLED",
        }
        actual = {s.name for s in TicketWorkflowState}
        assert actual == expected

    def test_valid_forward_transition(self):
        assert can_transition(TicketWorkflowState.DETECTED, TicketWorkflowState.ALLOCATION_SUGGESTED)

    def test_invalid_backward_transition(self):
        assert not can_transition(TicketWorkflowState.COMPLETED, TicketWorkflowState.DETECTED)

    def test_terminal_state_has_no_transitions(self):
        assert not can_transition(TicketWorkflowState.COMPLETION_NOTIFIED, TicketWorkflowState.DETECTED)
        assert not can_transition(TicketWorkflowState.CANCELLED, TicketWorkflowState.DETECTED)

    def test_failed_retryable_can_recover(self):
        assert can_transition(TicketWorkflowState.FAILED_RETRYABLE, TicketWorkflowState.DETECTED)
        assert can_transition(TicketWorkflowState.FAILED_RETRYABLE, TicketWorkflowState.ALLOCATION_SUGGESTED)
        assert can_transition(TicketWorkflowState.FAILED_RETRYABLE, TicketWorkflowState.ASSIGNED)

    def test_any_active_state_can_fail(self):
        for state in [
            TicketWorkflowState.DETECTED,
            TicketWorkflowState.ALLOCATION_SUGGESTED,
            TicketWorkflowState.ALLOCATION_APPROVED,
            TicketWorkflowState.ASSIGNED,
            TicketWorkflowState.IN_PROGRESS,
            TicketWorkflowState.COMPLETED,
        ]:
            assert can_transition(state, TicketWorkflowState.FAILED_RETRYABLE), f"{state.name} should be able to fail"

    def test_assigned_can_complete_directly(self):
        assert can_transition(TicketWorkflowState.ASSIGNED, TicketWorkflowState.COMPLETED)

    def test_assigned_can_go_in_progress(self):
        assert can_transition(TicketWorkflowState.ASSIGNED, TicketWorkflowState.IN_PROGRESS)


class TestAllocationStrategy:
    def test_values_match_config_strings(self):
        assert AllocationStrategy.SKILL_MATCH.value == "skill_match"
        assert AllocationStrategy.CURRENT_LOAD.value == "current_load"
        assert AllocationStrategy.HISTORICAL_LOAD.value == "historical_load"
        assert AllocationStrategy.ALPHABETICAL.value == "alphabetical"


class TestAuditAction:
    def test_all_expected_actions_exist(self):
        expected = {
            "ticket_detected",
            "baseline_created",
            "allocation_suggested",
            "coordinator_notified",
            "allocation_approved",
            "developer_notified",
            "status_changed",
            "completion_detected",
            "completion_notified",
            "notification_failed",
            "approval_timeout",
        }
        actual = {a.value for a in AuditAction}
        assert actual == expected


class TestNotificationType:
    def test_all_expected_types_exist(self):
        expected = {
            "new_ticket_alert",
            "allocation_suggestion",
            "assignment_notice",
            "completion_notice",
            "load_board",
            "test_message",
        }
        actual = {n.value for n in NotificationType}
        assert actual == expected
