"""Diagnostics support for Microsoft Teams Workflow Notify."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import TeamsWorkflowNotifyConfigEntry
from .const import CONF_WEBHOOK_URL

TO_REDACT = {CONF_WEBHOOK_URL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TeamsWorkflowNotifyConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "runtime": {
            "full_width": entry.runtime_data.full_width,
        },
    }
