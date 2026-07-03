"""Exceptions for Microsoft Teams Workflow Notify."""

from __future__ import annotations


class TeamsWorkflowNotifyError(Exception):
    """Base exception for the integration."""


class TeamsWorkflowAuthError(TeamsWorkflowNotifyError):
    """Raised when the webhook rejects the request."""


class TeamsWorkflowConnectionError(TeamsWorkflowNotifyError):
    """Raised when the webhook cannot be reached."""


class TeamsWorkflowResponseError(TeamsWorkflowNotifyError):
    """Raised when the webhook returns an unexpected response."""
