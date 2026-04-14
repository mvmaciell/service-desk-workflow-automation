# Backward-compatibility shim — canonical definitions live in domain/errors.py
from .domain.errors import (  # noqa: F401
    AuthenticationRequiredError,
    CollectionError,
    ConfigurationError,
    InvalidStateTransitionError,
    LockUnavailableError,
    MonitorError,
    NotificationError,
)
