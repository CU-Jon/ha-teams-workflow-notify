"""Config flow for Microsoft Teams Workflow Notify."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .card import build_simple_card_payload
from .client import TeamsWorkflowNotifyClient, validate_http_url
from .const import (
    ADAPTIVE_CARD_VERSIONS,
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
    DEFAULT_VERIFICATION_MESSAGE,
    DEFAULT_VERIFICATION_TITLE,
    DEFAULT_VERIFY_WEBHOOK,
    DOMAIN,
)
from .exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowResponseError,
)


def _string_or_default(value: str | None, default: str) -> str:
    """Return a stripped string or the default."""
    if value is None:
        return default
    cleaned = value.strip()
    return cleaned or default


def _get_entry_value(
    config_entry: config_entries.ConfigEntry, key: str, default: Any
) -> Any:
    """Return the effective value from options or data."""
    return config_entry.options.get(key, config_entry.data.get(key, default))


def _build_user_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build the user-step schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_WEBHOOK_URL,
                default=defaults.get(CONF_WEBHOOK_URL, ""),
            ): str,
            vol.Optional(
                CONF_ENTITY_NAME,
                default=defaults.get(CONF_ENTITY_NAME, DEFAULT_ENTITY_NAME),
            ): str,
            vol.Optional(
                CONF_DEFAULT_CARD_TITLE,
                default=defaults.get(CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE),
            ): str,
            vol.Optional(
                CONF_ADAPTIVE_CARD_VERSION,
                default=defaults.get(
                    CONF_ADAPTIVE_CARD_VERSION, DEFAULT_ADAPTIVE_CARD_VERSION
                ),
            ): vol.In(ADAPTIVE_CARD_VERSIONS),
            vol.Optional(
                CONF_FULL_WIDTH,
                default=defaults.get(CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
            ): bool,
            vol.Optional(
                CONF_VERIFY_WEBHOOK,
                default=defaults.get(CONF_VERIFY_WEBHOOK, DEFAULT_VERIFY_WEBHOOK),
            ): bool,
        }
    )


def _build_options_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build the options-step schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_WEBHOOK_URL,
                default=defaults.get(CONF_WEBHOOK_URL, ""),
            ): str,
            vol.Optional(
                CONF_ENTITY_NAME,
                default=defaults.get(CONF_ENTITY_NAME, DEFAULT_ENTITY_NAME),
            ): str,
            vol.Optional(
                CONF_DEFAULT_CARD_TITLE,
                default=defaults.get(CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE),
            ): str,
            vol.Optional(
                CONF_ADAPTIVE_CARD_VERSION,
                default=defaults.get(
                    CONF_ADAPTIVE_CARD_VERSION, DEFAULT_ADAPTIVE_CARD_VERSION
                ),
            ): vol.In(ADAPTIVE_CARD_VERSIONS),
            vol.Optional(
                CONF_FULL_WIDTH,
                default=defaults.get(CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
            ): bool,
            vol.Optional(
                CONF_VERIFY_WEBHOOK,
                default=defaults.get(CONF_VERIFY_WEBHOOK, DEFAULT_VERIFY_WEBHOOK),
            ): bool,
        }
    )


async def _async_verify_webhook(
    hass, webhook_url: str, adaptive_card_version: str, full_width: bool
) -> None:
    """Send a verification card to the webhook."""
    session = async_get_clientsession(hass)
    client = TeamsWorkflowNotifyClient(webhook_url, session)
    payload = build_simple_card_payload(
        title=DEFAULT_VERIFICATION_TITLE,
        message=DEFAULT_VERIFICATION_MESSAGE,
        adaptive_card_version=adaptive_card_version,
        full_width=full_width,
    )
    await client.async_send_payload(payload)


def _normalize_user_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and validate user input."""
    return {
        CONF_WEBHOOK_URL: validate_http_url(user_input[CONF_WEBHOOK_URL]),
        CONF_ENTITY_NAME: _string_or_default(
            user_input.get(CONF_ENTITY_NAME), DEFAULT_ENTITY_NAME
        ),
        CONF_DEFAULT_CARD_TITLE: _string_or_default(
            user_input.get(CONF_DEFAULT_CARD_TITLE), DEFAULT_CARD_TITLE
        ),
        CONF_ADAPTIVE_CARD_VERSION: user_input.get(
            CONF_ADAPTIVE_CARD_VERSION, DEFAULT_ADAPTIVE_CARD_VERSION
        ),
        CONF_FULL_WIDTH: user_input.get(CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
        CONF_VERIFY_WEBHOOK: user_input.get(
            CONF_VERIFY_WEBHOOK, DEFAULT_VERIFY_WEBHOOK
        ),
    }


def _normalize_options_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize options input."""
    return {
        CONF_WEBHOOK_URL: validate_http_url(user_input[CONF_WEBHOOK_URL]),
        CONF_ENTITY_NAME: _string_or_default(
            user_input.get(CONF_ENTITY_NAME), DEFAULT_ENTITY_NAME
        ),
        CONF_DEFAULT_CARD_TITLE: _string_or_default(
            user_input.get(CONF_DEFAULT_CARD_TITLE), DEFAULT_CARD_TITLE
        ),
        CONF_ADAPTIVE_CARD_VERSION: user_input.get(
            CONF_ADAPTIVE_CARD_VERSION, DEFAULT_ADAPTIVE_CARD_VERSION
        ),
        CONF_FULL_WIDTH: user_input.get(CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH),
        CONF_VERIFY_WEBHOOK: user_input.get(
            CONF_VERIFY_WEBHOOK, DEFAULT_VERIFY_WEBHOOK
        ),
    }


class TeamsWorkflowNotifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Microsoft Teams Workflow Notify."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_user_input(user_input)
                if normalized[CONF_VERIFY_WEBHOOK]:
                    await _async_verify_webhook(
                        self.hass,
                        normalized[CONF_WEBHOOK_URL],
                        normalized[CONF_ADAPTIVE_CARD_VERSION],
                        normalized[CONF_FULL_WIDTH],
                    )
            except ValueError:
                errors["base"] = "invalid_url"
            except TeamsWorkflowAuthError:
                errors["base"] = "invalid_auth"
            except (TeamsWorkflowConnectionError, TeamsWorkflowResponseError):
                errors["base"] = "cannot_connect"
            except TeamsWorkflowNotifyError:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=normalized[CONF_ENTITY_NAME],
                    data=normalized,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return TeamsWorkflowNotifyOptionsFlow(config_entry)


class TeamsWorkflowNotifyOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Microsoft Teams Workflow Notify."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the integration options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_options_input(user_input)
                if normalized[CONF_VERIFY_WEBHOOK]:
                    await _async_verify_webhook(
                        self.hass,
                        normalized[CONF_WEBHOOK_URL],
                        normalized[CONF_ADAPTIVE_CARD_VERSION],
                        normalized[CONF_FULL_WIDTH],
                    )
            except ValueError:
                errors["base"] = "invalid_url"
            except TeamsWorkflowAuthError:
                errors["base"] = "invalid_auth"
            except (TeamsWorkflowConnectionError, TeamsWorkflowResponseError):
                errors["base"] = "cannot_connect"
            except TeamsWorkflowNotifyError:
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=normalized[CONF_ENTITY_NAME],
                    data={
                        **self.config_entry.data,
                        CONF_WEBHOOK_URL: normalized[CONF_WEBHOOK_URL],
                    },
                )
                return self.async_create_entry(
                    title="",
                    data={
                        key: value
                        for key, value in normalized.items()
                        if key != CONF_WEBHOOK_URL
                    },
                )

        defaults = {
            CONF_WEBHOOK_URL: self.config_entry.data[CONF_WEBHOOK_URL],
            CONF_ENTITY_NAME: _get_entry_value(
                self.config_entry, CONF_ENTITY_NAME, DEFAULT_ENTITY_NAME
            ),
            CONF_DEFAULT_CARD_TITLE: _get_entry_value(
                self.config_entry, CONF_DEFAULT_CARD_TITLE, DEFAULT_CARD_TITLE
            ),
            CONF_ADAPTIVE_CARD_VERSION: _get_entry_value(
                self.config_entry,
                CONF_ADAPTIVE_CARD_VERSION,
                DEFAULT_ADAPTIVE_CARD_VERSION,
            ),
            CONF_FULL_WIDTH: _get_entry_value(
                self.config_entry, CONF_FULL_WIDTH, DEFAULT_FULL_WIDTH
            ),
            CONF_VERIFY_WEBHOOK: _get_entry_value(
                self.config_entry, CONF_VERIFY_WEBHOOK, DEFAULT_VERIFY_WEBHOOK
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(defaults),
            errors=errors,
        )
