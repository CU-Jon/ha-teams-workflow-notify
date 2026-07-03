"""Microsoft Teams Workflow Notify integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ACTIONS,
    ATTR_ACTION_URL,
    ATTR_FACTS,
    ATTR_FACT_VALUE,
    ATTR_SEVERITY,
    ATTR_SUBTITLE,
    CONF_ADAPTIVE_CARD_VERSION,
    CONF_DEFAULT_CARD_TITLE,
    CONF_ENTITY_NAME,
    CONF_FULL_WIDTH,
    CONF_VERIFY_WEBHOOK,
    CONF_WEBHOOK_URL,
    DEFAULT_ADAPTIVE_CARD_VERSION,
    DEFAULT_CARD_TITLE,
    DEFAULT_ENTITY_NAME,
    DEFAULT_FULL_WIDTH,
    DEFAULT_VERIFY_WEBHOOK,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_CARD,
    SEVERITIES,
    SEVERITY_DEFAULT,
)
from .coordinator import TeamsWorkflowNotifyRuntimeData

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType


def _entry_value(config_entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return the effective config entry value."""
    return config_entry.options.get(key, config_entry.data.get(key, default))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration and register services."""
    import voluptuous as vol

    from homeassistant.const import ATTR_ENTITY_ID
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import entity_registry as er

    from .client import validate_http_url

    hass.data.setdefault(DOMAIN, {})

    if hass.services.has_service(DOMAIN, SERVICE_SEND_CARD):
        return True

    facts_schema = vol.All(
        cv.ensure_list,
        [
            vol.Schema(
                {
                    vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
                    vol.Required(ATTR_FACT_VALUE): vol.All(
                        cv.string, vol.Length(min=1)
                    ),
                }
            )
        ],
    )
    actions_schema = vol.All(
        cv.ensure_list,
        [
            vol.Schema(
                {
                    vol.Required("title"): vol.All(cv.string, vol.Length(min=1)),
                    vol.Required(ATTR_ACTION_URL): vol.All(cv.string, validate_http_url),
                }
            )
        ],
    )
    service_schema = vol.Schema(
        {
            vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Optional("title"): cv.string,
            vol.Required("message"): vol.All(cv.string, vol.Length(min=1)),
            vol.Optional(ATTR_SUBTITLE): cv.string,
            vol.Optional(ATTR_SEVERITY, default=SEVERITY_DEFAULT): vol.In(SEVERITIES),
            vol.Optional(ATTR_FACTS): facts_schema,
            vol.Optional(ATTR_ACTIONS): actions_schema,
        }
    )

    async def async_handle_send_card(call: ServiceCall) -> None:
        """Handle the rich-card service call."""
        runtimes = _resolve_service_runtimes(
            hass,
            call,
            entity_registry=er.async_get(hass),
        )

        for runtime in runtimes:
            if runtime.entity is None:
                raise ServiceValidationError(
                    f"Notify entity for config entry {runtime.entry_id} is not available"
                )
            await runtime.entity.async_send_rich_card(
                title=call.data.get("title"),
                message=call.data["message"],
                subtitle=call.data.get(ATTR_SUBTITLE),
                severity=call.data.get(ATTR_SEVERITY, SEVERITY_DEFAULT),
                facts=call.data.get(ATTR_FACTS),
                actions=call.data.get(ATTR_ACTIONS),
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_CARD,
        async_handle_send_card,
        schema=service_schema,
    )
    return True


def _resolve_service_runtimes(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    entity_registry,
) -> list[TeamsWorkflowNotifyRuntimeData]:
    """Resolve which runtime entries a service call targets."""
    from homeassistant.const import ATTR_ENTITY_ID
    from homeassistant.exceptions import ServiceValidationError

    runtimes_by_entry: dict[str, TeamsWorkflowNotifyRuntimeData] = hass.data[DOMAIN]
    if not runtimes_by_entry:
        raise ServiceValidationError(
            "No Microsoft Teams Workflow Notify entries are configured"
        )

    entity_ids = call.data.get(ATTR_ENTITY_ID)
    if not entity_ids:
        if len(runtimes_by_entry) == 1:
            return list(runtimes_by_entry.values())
        raise ServiceValidationError(
            "Multiple Microsoft Teams Workflow Notify entries exist; specify target.entity_id"
        )

    selected_runtimes: list[TeamsWorkflowNotifyRuntimeData] = []
    seen_entry_ids: set[str] = set()
    for entity_id in entity_ids:
        registry_entry = entity_registry.async_get(entity_id)
        if registry_entry is None:
            raise ServiceValidationError(f"Entity {entity_id} was not found")

        runtime = runtimes_by_entry.get(registry_entry.config_entry_id)
        if runtime is None:
            raise ServiceValidationError(
                f"Entity {entity_id} does not belong to Microsoft Teams Workflow Notify"
            )

        if registry_entry.config_entry_id not in seen_entry_ids:
            selected_runtimes.append(runtime)
            seen_entry_ids.add(registry_entry.config_entry_id)

    return selected_runtimes


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Microsoft Teams Workflow Notify from a config entry."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .client import TeamsWorkflowNotifyClient

    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    runtime = TeamsWorkflowNotifyRuntimeData(
        entry_id=entry.entry_id,
        entity_name=_entry_value(entry, CONF_ENTITY_NAME, entry.title or DEFAULT_ENTITY_NAME),
        default_card_title=_entry_value(
            entry, CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE
        ),
        adaptive_card_version=_entry_value(
            entry, CONF_ADAPTIVE_CARD_VERSION, DEFAULT_ADAPTIVE_CARD_VERSION
        ),
        full_width=_entry_value(entry, CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
        verify_webhook=_entry_value(
            entry, CONF_VERIFY_WEBHOOK, DEFAULT_VERIFY_WEBHOOK
        ),
        client=TeamsWorkflowNotifyClient(entry.data[CONF_WEBHOOK_URL], session),
    )
    runtime.unload_callback = entry.add_update_listener(async_reload_entry)
    hass.data[DOMAIN][entry.entry_id] = runtime

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        if runtime.unload_callback is not None:
            runtime.unload_callback()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    runtime = hass.data[DOMAIN].get(entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    if runtime and runtime.unload_callback is not None:
        runtime.unload_callback()

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
