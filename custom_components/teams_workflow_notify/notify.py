"""Notify entity for Microsoft Teams Workflow Notify."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .card import build_rich_card_payload, build_simple_card_payload
from .const import DOMAIN, SEVERITY_DEFAULT
from .exceptions import TeamsWorkflowNotifyError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the notify entity from a config entry."""
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([TeamsWorkflowNotifyEntity(config_entry, runtime)])


class TeamsWorkflowNotifyEntity(NotifyEntity):
    """A Home Assistant notify entity for Teams workflow webhooks."""

    _attr_should_poll = False
    _attr_icon = "mdi:microsoft-teams"

    def __init__(self, config_entry: ConfigEntry, runtime) -> None:
        """Initialize the entity."""
        self._config_entry = config_entry
        self._runtime = runtime
        self._attr_unique_id = config_entry.entry_id
        self._attr_name = runtime.entity_name

    async def async_added_to_hass(self) -> None:
        """Register the entity in runtime data."""
        self._runtime.entity = self

    async def async_will_remove_from_hass(self) -> None:
        """Clear the entity reference from runtime data."""
        if self._runtime.entity is self:
            self._runtime.entity = None

    async def async_send_message(
        self, message: str, title: str | None = None
    ) -> None:
        """Send a simple card through notify.send_message."""
        payload = build_simple_card_payload(
            title=title or self._runtime.default_card_title,
            message=message,
            adaptive_card_version=self._runtime.adaptive_card_version,
            full_width=self._runtime.full_width,
        )
        await self._async_send_payload(payload)

    async def async_send_rich_card(
        self,
        *,
        message: str,
        title: str | None = None,
        subtitle: str | None = None,
        severity: str = SEVERITY_DEFAULT,
        facts: list[dict[str, str]] | None = None,
        actions: list[dict[str, str]] | None = None,
    ) -> None:
        """Send a richer Adaptive Card."""
        payload = build_rich_card_payload(
            title=title or self._runtime.default_card_title,
            message=message,
            subtitle=subtitle,
            severity=severity,
            facts=facts,
            actions=actions,
            adaptive_card_version=self._runtime.adaptive_card_version,
            full_width=self._runtime.full_width,
        )
        await self._async_send_payload(payload)

    async def _async_send_payload(self, payload: dict[str, Any]) -> None:
        """Send a payload and translate errors to Home Assistant errors."""
        try:
            await self._runtime.client.async_send_payload(payload)
        except TeamsWorkflowNotifyError as err:
            _LOGGER.error(
                "Failed to send Microsoft Teams Workflow notification for %s: %s",
                self.entity_id or self._attr_name,
                err,
            )
            raise HomeAssistantError(
                f"Failed to send Microsoft Teams Workflow notification: {err}"
            ) from err

        self._async_record_notification()
