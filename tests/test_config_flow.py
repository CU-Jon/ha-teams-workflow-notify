"""Tests for the integration config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.teams_workflow_notify.config_flow import (
    _async_verify_webhook,
    _string_or_default,
)
from custom_components.teams_workflow_notify.const import (
    CONF_DEFAULT_CARD_TITLE,
    CONF_ENTITY_NAME,
    CONF_FULL_WIDTH,
    CONF_WEBHOOK_URL,
    DOMAIN,
)
from custom_components.teams_workflow_notify.exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowResponseError,
)

WEBHOOK_URL = "https://example.logic.azure.com/workflows/one?sig=secret"
NEW_WEBHOOK_URL = "https://example.logic.azure.com/workflows/two?sig=secret"

USER_INPUT = {
    CONF_WEBHOOK_URL: WEBHOOK_URL,
    CONF_ENTITY_NAME: "Security channel",
    CONF_DEFAULT_CARD_TITLE: "My Home",
    CONF_FULL_WIDTH: False,
}

OPTIONS = {
    CONF_ENTITY_NAME: "Security channel",
    CONF_DEFAULT_CARD_TITLE: "My Home",
    CONF_FULL_WIDTH: False,
}


def _entry(webhook_url: str = WEBHOOK_URL) -> MockConfigEntry:
    """Create a current config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Security channel",
        data={CONF_WEBHOOK_URL: webhook_url},
        options=OPTIONS,
        version=1,
        minor_version=3,
    )


def test_string_normalization() -> None:
    """Missing and blank names should use a stable default."""
    assert _string_or_default(None, "Default") == "Default"
    assert _string_or_default("  ", "Default") == "Default"
    assert _string_or_default(" Name ", "Default") == "Name"


@pytest.mark.asyncio
async def test_webhook_verification_builds_visible_card(hass) -> None:
    """Verification should use the same client and card envelope as notifications."""
    client = MagicMock()
    client.async_send_payload = AsyncMock()
    session = MagicMock()

    with (
        patch(
            "custom_components.teams_workflow_notify.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.teams_workflow_notify.config_flow.TeamsWorkflowNotifyClient",
            return_value=client,
        ) as client_class,
    ):
        await _async_verify_webhook(hass, WEBHOOK_URL, False)

    client_class.assert_called_once_with(WEBHOOK_URL, session)
    payload = client.async_send_payload.await_args.args[0]
    content = payload["attachments"][0]["content"]
    assert content["body"][0]["text"] == "Microsoft Teams Workflow Notify"
    assert "msteams" not in content


@pytest.mark.asyncio
async def test_user_flow_creates_minimal_entry(hass) -> None:
    """A verified URL should be stored separately from mutable options."""
    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(),
    ) as verify:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Security channel"
    assert result["data"] == {CONF_WEBHOOK_URL: WEBHOOK_URL}
    assert result["options"] == OPTIONS
    verify.assert_awaited_once_with(hass, WEBHOOK_URL, False)


@pytest.mark.asyncio
async def test_user_flow_shows_form(hass) -> None:
    """Starting setup without input should show the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


@pytest.mark.asyncio
async def test_user_flow_rejects_invalid_url_without_request(hass) -> None:
    """Insecure URLs should fail before a visible verification notification."""
    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(),
    ) as verify:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={**USER_INPUT, CONF_WEBHOOK_URL: "http://example.com/hook"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_flow_aborts_duplicate_before_request(hass) -> None:
    """A duplicate webhook should not produce another verification card."""
    _entry().add_to_hass(hass)

    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(),
    ) as verify:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    verify.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (TeamsWorkflowAuthError(401), "invalid_auth"),
        (TeamsWorkflowConnectionError("timeout"), "cannot_connect"),
        (TeamsWorkflowResponseError(500), "cannot_connect"),
        (TeamsWorkflowNotifyError("bad payload"), "unknown"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_user_flow_maps_verification_errors(hass, exception, error: str) -> None:
    """Verification errors should be stable translation keys."""
    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(side_effect=exception),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


@pytest.mark.asyncio
async def test_options_flow_updates_title_and_defaults(hass) -> None:
    """Options should update presentation settings without exposing the URL."""
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    updated_options = {
        CONF_ENTITY_NAME: "Operations channel",
        CONF_DEFAULT_CARD_TITLE: "Operations",
        CONF_FULL_WIDTH: True,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], updated_options
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.title == "Operations channel"
    assert dict(entry.options) == updated_options


@pytest.mark.asyncio
async def test_reconfigure_updates_verified_url(hass) -> None:
    """Reconfigure should verify and replace only the secret URL."""
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == "reconfigure"

    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(),
    ) as verify:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_WEBHOOK_URL: NEW_WEBHOOK_URL}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dict(entry.data) == {CONF_WEBHOOK_URL: NEW_WEBHOOK_URL}
    assert dict(entry.options) == OPTIONS
    verify.assert_awaited_once_with(hass, NEW_WEBHOOK_URL, False)


@pytest.mark.asyncio
async def test_reconfigure_rejects_invalid_url(hass) -> None:
    """Reconfigure should retain the entry when a URL is invalid."""
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEBHOOK_URL: "http://example.com/hook"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}
    assert dict(entry.data) == {CONF_WEBHOOK_URL: WEBHOOK_URL}


@pytest.mark.asyncio
async def test_reconfigure_retains_entry_on_verification_error(hass) -> None:
    """Reconfigure should not save a URL rejected by the workflow."""
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(side_effect=TeamsWorkflowAuthError(403)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_WEBHOOK_URL: NEW_WEBHOOK_URL}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert dict(entry.data) == {CONF_WEBHOOK_URL: WEBHOOK_URL}


@pytest.mark.asyncio
async def test_reauth_updates_verified_url(hass) -> None:
    """Reauthentication should use the standard linked-entry flow."""
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=dict(entry.data),
    )
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.teams_workflow_notify.config_flow._async_verify_webhook",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_WEBHOOK_URL: NEW_WEBHOOK_URL}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert dict(entry.data) == {CONF_WEBHOOK_URL: NEW_WEBHOOK_URL}
