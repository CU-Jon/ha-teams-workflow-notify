"""Notify entity for Microsoft Teams Workflow Notify."""

from __future__ import annotations

import logging
from typing import Any, override

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TeamsWorkflowNotifyConfigEntry
from .card import build_rich_card_payload, build_simple_card_payload
from .client import serialize_payload
from .const import (
    DOMAIN,
    IMAGE_DELIVERY_AUTO,
    IMAGE_PAYLOAD_SAFETY_MARGIN_BYTES,
    MAX_PAYLOAD_SIZE_BYTES,
    SEVERITY_DEFAULT,
)
from .exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowExternalUrlUnavailableError,
    TeamsWorkflowImageTooLargeError,
    TeamsWorkflowInvalidImageError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowPayloadTooLargeError,
    TeamsWorkflowResponseError,
)
from .image import async_prepare_image

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TeamsWorkflowNotifyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the notify entity from a config entry."""
    async_add_entities([TeamsWorkflowNotifyEntity(config_entry)])


class TeamsWorkflowNotifyEntity(NotifyEntity):
    """A Home Assistant notify entity for Teams workflow webhooks."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:microsoft-teams"
    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, config_entry: TeamsWorkflowNotifyConfigEntry) -> None:
        """Initialize the entity."""
        self._config_entry = config_entry
        self._runtime = config_entry.runtime_data
        self._attr_unique_id = config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Microsoft",
            model="Teams workflow webhook",
            name=config_entry.title,
        )

    @override
    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a simple card through notify.send_message."""
        try:
            payload = build_simple_card_payload(
                title=title or self._runtime.default_card_title,
                message=message,
                full_width=self._runtime.full_width,
            )
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_message",
            ) from err

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
        image_url: str | None = None,
        image_alt_text: str | None = None,
        image_delivery: str = IMAGE_DELIVERY_AUTO,
    ) -> None:
        """Send a richer Adaptive Card."""
        effective_title = title or self._runtime.default_card_title
        prepared_image = image_url
        try:
            if image_url is not None:
                probe_payload = build_rich_card_payload(
                    title=effective_title,
                    message=message,
                    subtitle=subtitle,
                    severity=severity,
                    facts=facts,
                    actions=actions,
                    image_url="x",
                    image_alt_text=image_alt_text,
                    full_width=self._runtime.full_width,
                )
                image_overhead = len(serialize_payload(probe_payload)) - 1
                prepared_image = await async_prepare_image(
                    self.hass,
                    image_url,
                    image_delivery,
                    MAX_PAYLOAD_SIZE_BYTES
                    - IMAGE_PAYLOAD_SAFETY_MARGIN_BYTES
                    - image_overhead,
                )

            payload = build_rich_card_payload(
                title=effective_title,
                message=message,
                subtitle=subtitle,
                severity=severity,
                facts=facts,
                actions=actions,
                image_url=prepared_image,
                image_alt_text=image_alt_text,
                full_width=self._runtime.full_width,
            )
        except TeamsWorkflowInvalidImageError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_image",
            ) from err
        except TeamsWorkflowImageTooLargeError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="image_too_large",
            ) from err
        except TeamsWorkflowExternalUrlUnavailableError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="external_image_url_unavailable",
            ) from err
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_message",
            ) from err

        await self._async_send_payload(payload)
        self._async_record_notification()

    async def _async_send_payload(self, payload: dict[str, Any]) -> None:
        """Send a payload and translate errors to Home Assistant errors."""
        try:
            await self._runtime.client.async_send_payload(payload)
        except TeamsWorkflowPayloadTooLargeError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="payload_too_large",
                translation_placeholders={
                    "size": str(err.size),
                    "limit": str(MAX_PAYLOAD_SIZE_BYTES),
                },
            ) from err
        except TeamsWorkflowAuthError as err:
            self._config_entry.async_start_reauth_if_available(self.hass)
            _LOGGER.warning(
                "Teams workflow webhook rejected a request for %s with status %s",
                self.entity_id,
                err.status,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="authentication_failed",
            ) from err
        except TeamsWorkflowResponseError as err:
            _LOGGER.warning(
                "Teams workflow webhook returned status %s for %s",
                err.status,
                self.entity_id,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="response_error",
                translation_placeholders={"status": str(err.status)},
            ) from err
        except TeamsWorkflowConnectionError as err:
            _LOGGER.warning(
                "Could not reach the Teams workflow webhook for %s (%s)",
                self.entity_id,
                err.reason,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="connection_error",
            ) from err
        except TeamsWorkflowNotifyError as err:
            _LOGGER.warning(
                "Could not send a Teams workflow notification for %s",
                self.entity_id,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
            ) from err
