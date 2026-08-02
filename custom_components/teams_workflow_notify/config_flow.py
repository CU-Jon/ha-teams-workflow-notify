"""Config flow for Microsoft Teams Workflow Notify."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .card import build_simple_card_payload
from .client import TeamsWorkflowNotifyClient, validate_webhook_url
from .const import (
    CONF_DEFAULT_CARD_TITLE,
    CONF_ENTITY_NAME,
    CONF_FULL_WIDTH,
    CONF_WEBHOOK_URL,
    DEFAULT_CARD_TITLE,
    DEFAULT_ENTITY_NAME,
    DEFAULT_FULL_WIDTH,
    DEFAULT_VERIFICATION_MESSAGE,
    DEFAULT_VERIFICATION_TITLE,
    DOMAIN,
)
from .exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowResponseError,
)

_LOGGER = logging.getLogger(__name__)

_TEXT_SELECTOR = selector.TextSelector(selector.TextSelectorConfig())
_URL_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
)
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WEBHOOK_URL): _URL_SELECTOR,
        vol.Optional(CONF_ENTITY_NAME, default=DEFAULT_ENTITY_NAME): _TEXT_SELECTOR,
        vol.Optional(
            CONF_DEFAULT_CARD_TITLE, default=DEFAULT_CARD_TITLE
        ): _TEXT_SELECTOR,
        vol.Optional(
            CONF_FULL_WIDTH, default=DEFAULT_FULL_WIDTH
        ): selector.BooleanSelector(),
    }
)

WEBHOOK_SCHEMA = vol.Schema({vol.Required(CONF_WEBHOOK_URL): _URL_SELECTOR})

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTITY_NAME, default=DEFAULT_ENTITY_NAME): _TEXT_SELECTOR,
        vol.Optional(
            CONF_DEFAULT_CARD_TITLE, default=DEFAULT_CARD_TITLE
        ): _TEXT_SELECTOR,
        vol.Optional(
            CONF_FULL_WIDTH, default=DEFAULT_FULL_WIDTH
        ): selector.BooleanSelector(),
    }
)


def _string_or_default(value: str | None, default: str) -> str:
    """Return a stripped string or the default."""
    if value is None:
        return default
    return value.strip() or default


def _entry_value(config_entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return the effective value from options or data."""
    return config_entry.options.get(key, config_entry.data.get(key, default))


def _normalize_card_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize card and entity settings."""
    return {
        CONF_ENTITY_NAME: _string_or_default(
            user_input.get(CONF_ENTITY_NAME), DEFAULT_ENTITY_NAME
        ),
        CONF_DEFAULT_CARD_TITLE: _string_or_default(
            user_input.get(CONF_DEFAULT_CARD_TITLE), DEFAULT_CARD_TITLE
        ),
        CONF_FULL_WIDTH: user_input.get(CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
    }


async def _async_verify_webhook(
    hass: HomeAssistant,
    webhook_url: str,
    full_width: bool,
) -> None:
    """Send a verification card to the webhook."""
    client = TeamsWorkflowNotifyClient(webhook_url, async_get_clientsession(hass))
    payload = build_simple_card_payload(
        title=DEFAULT_VERIFICATION_TITLE,
        message=DEFAULT_VERIFICATION_MESSAGE,
        full_width=full_width,
    )
    await client.async_send_payload(payload)


async def _async_check_webhook(
    hass: HomeAssistant,
    webhook_url: str,
    *,
    full_width: bool,
) -> str | None:
    """Verify a normalized webhook and return any form error."""
    try:
        await _async_verify_webhook(
            hass,
            webhook_url,
            full_width,
        )
    except TeamsWorkflowAuthError:
        return "invalid_auth"
    except (TeamsWorkflowConnectionError, TeamsWorkflowResponseError):
        return "cannot_connect"
    except TeamsWorkflowNotifyError:
        return "unknown"
    except Exception as err:
        _LOGGER.error(
            "Unexpected error verifying Teams workflow webhook (%s)",
            err.__class__.__name__,
        )
        return "unknown"

    return None


class TeamsWorkflowNotifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Microsoft Teams Workflow Notify."""

    VERSION = 1
    MINOR_VERSION = 3

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            card_settings = _normalize_card_input(user_input)
            try:
                webhook_url = validate_webhook_url(user_input[CONF_WEBHOOK_URL])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                self._async_abort_entries_match({CONF_WEBHOOK_URL: webhook_url})
                if error := await _async_check_webhook(
                    self.hass,
                    webhook_url,
                    full_width=card_settings[CONF_FULL_WIDTH],
                ):
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title=card_settings[CONF_ENTITY_NAME],
                        data={CONF_WEBHOOK_URL: webhook_url},
                        options=card_settings,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @override
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update and verify a webhook URL."""
        entry = self._get_reconfigure_entry()
        return await self._async_webhook_update_step("reconfigure", entry, user_input)

    @override
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication for a rejected webhook."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace and verify a rejected webhook URL."""
        entry = self._get_reauth_entry()
        return await self._async_webhook_update_step(
            "reauth_confirm", entry, user_input
        )

    async def _async_webhook_update_step(
        self,
        step_id: str,
        entry: ConfigEntry,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Handle a reconfigure or reauthentication webhook update."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                webhook_url = validate_webhook_url(user_input[CONF_WEBHOOK_URL])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                self._async_abort_entries_match({CONF_WEBHOOK_URL: webhook_url})
                if error := await _async_check_webhook(
                    self.hass,
                    webhook_url,
                    full_width=_entry_value(entry, CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
                ):
                    errors["base"] = error
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={CONF_WEBHOOK_URL: webhook_url},
                    )

        suggestions = user_input or {CONF_WEBHOOK_URL: entry.data[CONF_WEBHOOK_URL]}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                WEBHOOK_SCHEMA, suggestions
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return TeamsWorkflowNotifyOptionsFlow()


class TeamsWorkflowNotifyOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle mutable display and card options."""

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            options = _normalize_card_input(user_input)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=options[CONF_ENTITY_NAME],
            )
            return self.async_create_entry(title="", data=options)

        suggestions = {
            CONF_ENTITY_NAME: self.config_entry.title,
            CONF_DEFAULT_CARD_TITLE: _entry_value(
                self.config_entry, CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE
            ),
            CONF_FULL_WIDTH: _entry_value(
                self.config_entry, CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, suggestions
            ),
        )
