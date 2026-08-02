"""Exceptions for Microsoft Teams Workflow Notify."""

from __future__ import annotations


class TeamsWorkflowNotifyError(Exception):
    """Base exception for the integration."""


class TeamsWorkflowAuthError(TeamsWorkflowNotifyError):
    """Raised when the webhook rejects the request."""

    def __init__(self, status: int) -> None:
        """Initialize the error."""
        self.status = status
        super().__init__(f"Webhook authentication failed with status {status}")


class TeamsWorkflowConnectionError(TeamsWorkflowNotifyError):
    """Raised when the webhook cannot be reached."""

    def __init__(self, reason: str) -> None:
        """Initialize the error."""
        self.reason = reason
        super().__init__(f"Webhook connection failed ({reason})")


class TeamsWorkflowResponseError(TeamsWorkflowNotifyError):
    """Raised when the webhook returns an unexpected response."""

    def __init__(self, status: int) -> None:
        """Initialize the error."""
        self.status = status
        super().__init__(f"Webhook returned status {status}")


class TeamsWorkflowPayloadTooLargeError(TeamsWorkflowNotifyError):
    """Raised when a payload exceeds the Microsoft Teams connector limit."""

    def __init__(self, size: int, limit: int) -> None:
        """Initialize the error."""
        self.size = size
        self.limit = limit
        super().__init__(f"Payload is {size} bytes; limit is {limit} bytes")


class TeamsWorkflowInvalidImageError(TeamsWorkflowNotifyError):
    """Raised when a card image source cannot be safely used."""


class TeamsWorkflowImageTooLargeError(TeamsWorkflowNotifyError):
    """Raised when a local image cannot fit in the card payload."""


class TeamsWorkflowExternalUrlUnavailableError(TeamsWorkflowNotifyError):
    """Raised when a local image cannot be exposed using an external URL."""
