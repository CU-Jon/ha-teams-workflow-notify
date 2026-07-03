"""Runtime data for Microsoft Teams Workflow Notify."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import TeamsWorkflowNotifyClient
    from .notify import TeamsWorkflowNotifyEntity


@dataclass(slots=True)
class TeamsWorkflowNotifyRuntimeData:
    """Runtime data stored for each config entry."""

    entry_id: str
    entity_name: str
    default_card_title: str
    adaptive_card_version: str
    full_width: bool
    verify_webhook: bool
    client: TeamsWorkflowNotifyClient
    unload_callback: Callable[[], None] | None = None
    entity: TeamsWorkflowNotifyEntity | None = None
