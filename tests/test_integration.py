"""Tests for integration setup, migration, diagnostics, and services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import DATA_DOMAIN_PLATFORM_ENTITIES
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.teams_workflow_notify import (
    SEND_CARD_SCHEMA,
    async_migrate_entry,
    async_setup,
)
from custom_components.teams_workflow_notify.const import (
    CONF_DEFAULT_CARD_TITLE,
    CONF_ENTITY_NAME,
    CONF_FULL_WIDTH,
    CONF_WEBHOOK_URL,
    DOMAIN,
    SERVICE_SEND_CARD,
)
from custom_components.teams_workflow_notify.diagnostics import (
    async_get_config_entry_diagnostics,
)

WEBHOOK_URL = "https://example.logic.azure.com/workflows/one?sig=secret"
PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP4z8AAAAMBAQ"
    "D3A0FDAAAAAElFTkSuQmCC"
)

OPTIONS = {
    CONF_ENTITY_NAME: "Security channel",
    CONF_DEFAULT_CARD_TITLE: "My Home",
    CONF_FULL_WIDTH: False,
}


def _entry() -> MockConfigEntry:
    """Create a current config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Security channel",
        data={CONF_WEBHOOK_URL: WEBHOOK_URL},
        options=OPTIONS,
        version=1,
        minor_version=3,
    )


async def _setup_entry(hass) -> tuple[MockConfigEntry, str]:
    """Set up a config entry and return its notify entity ID."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    registry_entries = er.async_entries_for_config_entry(
        er.async_get(hass), entry.entry_id
    )
    assert len(registry_entries) == 1
    return entry, registry_entries[0].entity_id


@pytest.mark.asyncio
async def test_setup_creates_service_device_and_notify_entity(hass) -> None:
    """Setup should use config-entry runtime data and a service device."""
    entry, entity_id = await _setup_entry(hass)

    assert hass.services.has_service(DOMAIN, SERVICE_SEND_CARD)
    assert hass.states.get(entity_id) is not None
    assert entry.runtime_data.default_card_title == "My Home"
    assert entry.runtime_data.full_width is False

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.manufacturer == "Microsoft"
    assert device.name == "Security channel"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.asyncio
async def test_setup_is_idempotent(hass) -> None:
    """Repeated integration setup should not register the service twice."""
    assert await async_setup(hass, {})
    service = hass.services.async_services()[DOMAIN][SERVICE_SEND_CARD]
    assert await async_setup(hass, {})
    assert hass.services.async_services()[DOMAIN][SERVICE_SEND_CARD] is service


@pytest.mark.asyncio
async def test_send_card_targets_only_integration_entity(hass) -> None:
    """The platform entity service should send and record a rich card."""
    entry, entity_id = await _setup_entry(hass)
    send = AsyncMock()
    entry.runtime_data.client.async_send_payload = send

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_CARD,
        {
            ATTR_ENTITY_ID: [entity_id],
            "title": "Garage",
            "message": "Door open",
            "subtitle": "Home Assistant",
            "severity": "warning",
            "facts": [{"title": "Entity", "value": "cover.garage"}],
            "actions": [{"title": "Open", "url": "https://ha.example.com"}],
            "image_url": PNG_DATA_URI,
            "image_alt_text": "Garage camera snapshot",
        },
        blocking=True,
    )

    send.assert_awaited_once()
    card = send.await_args.args[0]["attachments"][0]["content"]
    assert card["body"][0]["text"] == "Home Assistant"
    assert card["body"][1]["color"] == "warning"
    assert card["body"][-2]["type"] == "Image"
    assert card["body"][-2]["altText"] == "Garage camera snapshot"
    assert card["body"][-1]["type"] == "FactSet"
    assert card["actions"][0]["type"] == "Action.OpenUrl"
    assert hass.states.get(entity_id).state != "unknown"


@pytest.mark.asyncio
async def test_standard_notify_action_sends_simple_card(hass) -> None:
    """The native notify action should pass title and message to the entity."""
    entry, entity_id = await _setup_entry(hass)
    send = AsyncMock()
    entry.runtime_data.client.async_send_payload = send

    await hass.services.async_call(
        Platform.NOTIFY,
        "send_message",
        {
            ATTR_ENTITY_ID: [entity_id],
            "title": "Garage",
            "message": "Door open",
        },
        blocking=True,
    )

    send.assert_awaited_once()
    card = send.await_args.args[0]["attachments"][0]["content"]
    assert card["body"][0]["text"] == "Garage"
    assert card["body"][1]["text"] == "Door open"


@pytest.mark.asyncio
async def test_diagnostics_redact_webhook(hass) -> None:
    """Downloaded diagnostics should never expose the workflow URL."""
    entry, _ = await _setup_entry(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    serialized = str(diagnostics)
    assert WEBHOOK_URL not in serialized
    assert "**REDACTED**" in serialized
    assert diagnostics["runtime"] == {"full_width": False}


@pytest.mark.asyncio
async def test_migrate_legacy_entry(hass) -> None:
    """Legacy mixed storage should migrate to secret data and mutable options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old title",
        data={
            CONF_WEBHOOK_URL: WEBHOOK_URL,
            CONF_ENTITY_NAME: "Migrated channel",
            CONF_DEFAULT_CARD_TITLE: "Migrated home",
            "adaptive_card_version": "1.3",
            CONF_FULL_WIDTH: True,
            "verify_webhook": False,
        },
        options={},
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 1
    assert entry.minor_version == 3
    assert entry.title == "Migrated channel"
    assert dict(entry.data) == {CONF_WEBHOOK_URL: WEBHOOK_URL}
    assert dict(entry.options) == {
        CONF_ENTITY_NAME: "Migrated channel",
        CONF_DEFAULT_CARD_TITLE: "Migrated home",
        CONF_FULL_WIDTH: True,
    }


@pytest.mark.asyncio
async def test_migrate_removes_configurable_card_version(hass) -> None:
    """The 1.3 migration should remove a previously stored version choice."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Security channel",
        data={CONF_WEBHOOK_URL: WEBHOOK_URL},
        options={**OPTIONS, "adaptive_card_version": "1.5"},
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.minor_version == 3
    assert dict(entry.options) == OPTIONS


@pytest.mark.asyncio
async def test_migration_rejects_unknown_major_version(hass) -> None:
    """Unknown future storage layouts should not be modified."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Future",
        data={CONF_WEBHOOK_URL: WEBHOOK_URL},
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert not await async_migrate_entry(hass, entry)


@pytest.mark.asyncio
async def test_current_entry_does_not_need_migration(hass) -> None:
    """A current entry should pass migration without being rewritten."""
    entry = _entry()
    entry.add_to_hass(hass)
    original_data = dict(entry.data)
    original_options = dict(entry.options)

    assert await async_migrate_entry(hass, entry)
    assert dict(entry.data) == original_data
    assert dict(entry.options) == original_options


@pytest.mark.asyncio
async def test_setup_rejects_legacy_insecure_url(hass) -> None:
    """Invalid stored URLs should fail setup with a translated config error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Insecure",
        data={CONF_WEBHOOK_URL: "http://example.com/hook"},
        options=OPTIONS,
        version=1,
        minor_version=3,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.teams_workflow_notify.TeamsWorkflowNotifyClient",
        side_effect=ValueError("invalid"),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


def test_platform_runtime_index_is_integration_scoped() -> None:
    """Document the key used by the platform-aware entity service helper."""
    assert (Platform.NOTIFY, DOMAIN) == ("notify", "teams_workflow_notify")
    assert DATA_DOMAIN_PLATFORM_ENTITIES is not None


def test_send_card_schema_enforces_teams_action_limit() -> None:
    """The service schema should accept six actions and reject a seventh."""
    schema = vol.Schema(SEND_CARD_SCHEMA)
    actions = [
        {"title": f"Action {index}", "url": f"https://example.com/{index}"}
        for index in range(6)
    ]

    assert len(schema({"message": "Test", "actions": actions})["actions"]) == 6
    with pytest.raises(vol.Invalid):
        schema(
            {
                "message": "Test",
                "actions": [
                    *actions,
                    {"title": "Action 7", "url": "https://example.com/7"},
                ],
            }
        )
