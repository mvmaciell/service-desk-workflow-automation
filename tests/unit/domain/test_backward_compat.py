"""Tests that the backward-compatibility shims work correctly."""


class TestModelsShim:
    def test_ticket_importable_from_root(self):
        from src.megahub_monitor.models import Ticket
        assert Ticket is not None

    def test_load_entry_importable_from_root(self):
        from src.megahub_monitor.models import LoadEntry
        assert LoadEntry is not None

    def test_detection_result_importable_from_root(self):
        from src.megahub_monitor.models import DetectionResult
        assert DetectionResult is not None

    def test_delivery_request_importable_from_root(self):
        from src.megahub_monitor.models import DeliveryRequest
        assert DeliveryRequest is not None

    def test_notification_result_importable_from_root(self):
        from src.megahub_monitor.models import NotificationResult
        assert NotificationResult is not None

    def test_utc_now_iso_importable_from_root(self):
        from src.megahub_monitor.models import utc_now_iso
        result = utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result


class TestErrorsShim:
    def test_monitor_error_importable_from_root(self):
        from src.megahub_monitor.errors import MonitorError
        assert issubclass(MonitorError, Exception)

    def test_all_errors_importable_from_root(self):
        from src.megahub_monitor.errors import (
            AuthenticationRequiredError,
            CollectionError,
            ConfigurationError,
            LockUnavailableError,
            NotificationError,
        )
        for cls in [ConfigurationError, AuthenticationRequiredError, CollectionError, NotificationError, LockUnavailableError]:
            assert issubclass(cls, Exception)

    def test_new_error_also_available_from_root(self):
        from src.megahub_monitor.errors import InvalidStateTransitionError
        assert issubclass(InvalidStateTransitionError, Exception)


class TestIdentityPreserved:
    def test_same_ticket_class(self):
        from src.megahub_monitor.domain.models import Ticket as DomainTicket
        from src.megahub_monitor.models import Ticket as RootTicket
        assert DomainTicket is RootTicket

    def test_same_error_class(self):
        from src.megahub_monitor.domain.errors import MonitorError as DomainError
        from src.megahub_monitor.errors import MonitorError as RootError
        assert DomainError is RootError
