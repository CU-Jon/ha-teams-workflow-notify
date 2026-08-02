"""Tests for notify-entity error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import DATA_DOMAIN_PLATFORM_ENTITIES
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    TeamsWorkflowExternalUrlUnavailableError,
    TeamsWorkflowImageTooLargeError,
    TeamsWorkflowInvalidImageError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowPayloadTooLargeError,
    TeamsWorkflowResponseError,
)

WEBHOOK_URL = "https://example.logic.azure.com/workflows/one?sig=secret"


async def _setup_entity(hass):
    """Set up and return an entry and its entity object."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Security channel",
        data={CONF_WEBHOOK_URL: WEBHOOK_URL},
        options={
            CONF_ENTITY_NAME: "Security channel",
            CONF_DEFAULT_CARD_TITLE: "My Home",
            CONF_FULL_WIDTH: True,
        },
        version=1,
        minor_version=3,
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    entities = hass.data[DATA_DOMAIN_PLATFORM_ENTITIES][(Platform.NOTIFY, DOMAIN)]
    return entry, next(iter(entities.values()))


@pytest.mark.asyncio
async def test_simple_message_rejects_blank_input(hass) -> None:
    """A blank native notify message should raise a translated validation error."""
    _, entity = await _setup_entity(hass)

    with pytest.raises(ServiceValidationError) as error:
        await entity.async_send_message("   ")

    assert error.value.translation_key == "invalid_message"


@pytest.mark.asyncio
async def test_rich_card_uses_default_title_and_records_notification(hass) -> None:
    """Direct rich-card sends should apply defaults and update notify state."""
    entry, entity = await _setup_entity(hass)
    send = AsyncMock()
    entry.runtime_data.client.async_send_payload = send
    old_state = entity.state

    await entity.async_send_rich_card(message="Everything is nominal")

    content = send.await_args.args[0]["attachments"][0]["content"]
    assert content["body"][0]["text"] == "My Home"
    assert entity.state != old_state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "translation_key"),
    [
        (TeamsWorkflowInvalidImageError(), "invalid_image"),
        (TeamsWorkflowImageTooLargeError(), "image_too_large"),
        (
            TeamsWorkflowExternalUrlUnavailableError(),
            "external_image_url_unavailable",
        ),
    ],
)
async def test_image_errors_are_translated(
    hass,
    exception: Exception,
    translation_key: str,
) -> None:
    """Image preparation failures should become stable validation errors."""
    _, entity = await _setup_entity(hass)

    with (
        patch(
            "custom_components.teams_workflow_notify.notify.async_prepare_image",
            AsyncMock(side_effect=exception),
        ),
        pytest.raises(ServiceValidationError) as error,
    ):
        await entity.async_send_rich_card(
            message="Camera event",
            image_url="/local/camera.png",
        )

    assert error.value.translation_key == translation_key


@pytest.mark.asyncio
async def test_rich_card_rejects_blank_message(hass) -> None:
    """Direct rich-card calls should translate card validation failures."""
    _, entity = await _setup_entity(hass)

    with pytest.raises(ServiceValidationError) as error:
        await entity.async_send_rich_card(message="   ")

    assert error.value.translation_key == "invalid_message"


@pytest.mark.asyncio
async def test_auth_error_starts_reauthentication(hass) -> None:
    """A rejected webhook should start the standard repair flow."""
    entry, entity = await _setup_entity(hass)
    entry.runtime_data.client.async_send_payload = AsyncMock(
        side_effect=TeamsWorkflowAuthError(401)
    )

    with patch.object(entry, "async_start_reauth_if_available") as start_reauth:
        with pytest.raises(HomeAssistantError) as error:
            await entity.async_send_message("Message")

    assert error.value.translation_key == "authentication_failed"
    start_reauth.assert_called_once_with(hass)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "exception_type", "translation_key"),
    [
        (
            TeamsWorkflowPayloadTooLargeError(30000, 28672),
            ServiceValidationError,
            "payload_too_large",
        ),
        (
            TeamsWorkflowResponseError(500),
            HomeAssistantError,
            "response_error",
        ),
        (
            TeamsWorkflowConnectionError("timeout"),
            HomeAssistantError,
            "connection_error",
        ),
        (
            TeamsWorkflowNotifyError("serialization"),
            HomeAssistantError,
            "send_failed",
        ),
    ],
)
async def test_send_errors_are_translated(
    hass,
    exception: Exception,
    exception_type: type[Exception],
    translation_key: str,
) -> None:
    """Client errors should become stable, translatable Home Assistant errors."""
    entry, entity = await _setup_entity(hass)
    entry.runtime_data.client.async_send_payload = AsyncMock(side_effect=exception)

    with pytest.raises(exception_type) as error:
        await entity.async_send_message("Message")

    assert error.value.translation_key == translation_key
