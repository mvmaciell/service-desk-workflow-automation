# Backward-compatibility shim — canonical definitions live in domain/models.py
from .domain.models import (  # noqa: F401
    DeliveryRequest,
    DetectionResult,
    LoadEntry,
    NotificationResult,
    Ticket,
    utc_now_iso,
)

