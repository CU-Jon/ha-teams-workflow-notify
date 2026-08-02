"""Data models for Microsoft Teams Workflow Notify."""

from __future__ import annotations

from dataclasses import dataclass

from .client import TeamsWorkflowNotifyClient


@dataclass(slots=True)
class TeamsWorkflowNotifyRuntimeData:
    """Runtime data stored on a config entry."""

    client: TeamsWorkflowNotifyClient
    default_card_title: str
    full_width: bool
