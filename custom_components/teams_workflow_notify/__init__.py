"""Microsoft Teams Workflow Notify integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.notify.const import ATTR_MESSAGE, ATTR_TITLE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_platform_entity_service
from homeassistant.helpers.typing import ConfigType

from .client import TeamsWorkflowNotifyClient, validate_http_url, validate_image_url
from .const import (
    ATTR_ACTION_URL,
    ATTR_ACTIONS,
    ATTR_FACT_VALUE,
    ATTR_FACTS,
    ATTR_IMAGE_ALT_TEXT,
    ATTR_IMAGE_DELIVERY,
    ATTR_IMAGE_URL,
    ATTR_SEVERITY,
    ATTR_SUBTITLE,
    CONF_DEFAULT_CARD_TITLE,
    CONF_ENTITY_NAME,
    CONF_FULL_WIDTH,
    CONF_WEBHOOK_URL,
    DEFAULT_CARD_TITLE,
    DEFAULT_ENTITY_NAME,
    DEFAULT_FULL_WIDTH,
    DOMAIN,
    IMAGE_DELIVERY_AUTO,
    IMAGE_DELIVERY_MODES,
    SERVICE_SEND_CARD,
    SEVERITIES,
    SEVERITY_DEFAULT,
)
from .models import TeamsWorkflowNotifyRuntimeData

PLATFORMS: tuple[Platform, ...] = (Platform.NOTIFY,)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type TeamsWorkflowNotifyConfigEntry = ConfigEntry[TeamsWorkflowNotifyRuntimeData]


def _entry_value(config_entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return the effective config entry value."""
    return config_entry.options.get(key, config_entry.data.get(key, default))


FACTS_SCHEMA = vol.All(
    cv.ensure_list,
    [
        vol.Schema(
            {
                vol.Required(ATTR_TITLE): vol.All(cv.string, vol.Length(min=1)),
                vol.Required(ATTR_FACT_VALUE): vol.All(cv.string, vol.Length(min=1)),
            }
        )
    ],
)

ACTIONS_SCHEMA = vol.All(
    cv.ensure_list,
    vol.Length(max=6),
    [
        vol.Schema(
            {
                vol.Required(ATTR_TITLE): vol.All(cv.string, vol.Length(min=1)),
                vol.Required(ATTR_ACTION_URL): vol.All(cv.string, validate_http_url),
            }
        )
    ],
)

SEND_CARD_SCHEMA = {
    vol.Optional(ATTR_TITLE): cv.string,
    vol.Required(ATTR_MESSAGE): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional(ATTR_SUBTITLE): cv.string,
    vol.Optional(ATTR_SEVERITY, default=SEVERITY_DEFAULT): vol.In(SEVERITIES),
    vol.Optional(ATTR_FACTS): FACTS_SCHEMA,
    vol.Optional(ATTR_ACTIONS): ACTIONS_SCHEMA,
    vol.Optional(ATTR_IMAGE_URL): vol.All(cv.string, validate_image_url),
    vol.Optional(ATTR_IMAGE_ALT_TEXT): cv.string,
    vol.Optional(ATTR_IMAGE_DELIVERY, default=IMAGE_DELIVERY_AUTO): vol.In(
        IMAGE_DELIVERY_MODES
    ),
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration and register its entity service."""
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_CARD):
        async_register_platform_entity_service(
            hass,
            DOMAIN,
            SERVICE_SEND_CARD,
            entity_domain=Platform.NOTIFY,
            func="async_send_rich_card",
            schema=SEND_CARD_SCHEMA,
        )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: TeamsWorkflowNotifyConfigEntry
) -> bool:
    """Set up Microsoft Teams Workflow Notify from a config entry."""
    try:
        client = TeamsWorkflowNotifyClient(
            entry.data[CONF_WEBHOOK_URL], async_get_clientsession(hass)
        )
    except ValueError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_webhook_url",
        ) from err

    entry.runtime_data = TeamsWorkflowNotifyRuntimeData(
        client=client,
        default_card_title=_entry_value(
            entry, CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE
        ),
        full_width=_entry_value(entry, CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: TeamsWorkflowNotifyConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry data to the current storage layout."""
    if entry.version != 1:
        return False

    if entry.minor_version < 3:
        webhook_url = _entry_value(entry, CONF_WEBHOOK_URL, "")
        title = _entry_value(
            entry,
            CONF_ENTITY_NAME,
            entry.title or DEFAULT_ENTITY_NAME,
        )
        options = {
            CONF_ENTITY_NAME: title,
            CONF_DEFAULT_CARD_TITLE: _entry_value(
                entry, CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE
            ),
            CONF_FULL_WIDTH: _entry_value(entry, CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
        }
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_WEBHOOK_URL: webhook_url},
            options=options,
            title=title,
            version=1,
            minor_version=3,
        )

    return True
