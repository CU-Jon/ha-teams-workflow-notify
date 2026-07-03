"""Tests for the Adaptive Card builders."""

from __future__ import annotations

from custom_components.teams_workflow_notify.card import (
    build_rich_card_payload,
    build_simple_card_payload,
)


def _card_content(payload: dict) -> dict:
    return payload["attachments"][0]["content"]


def test_simple_card_includes_title_and_message() -> None:
    payload = build_simple_card_payload(
        title="Garage Door",
        message="Garage has been open for 20 minutes.",
        adaptive_card_version="1.2",
        full_width=True,
    )

    content = _card_content(payload)
    assert payload["type"] == "message"
    assert content["body"][0]["text"] == "Garage Door"
    assert content["body"][1]["text"] == "Garage has been open for 20 minutes."


def test_full_width_true_includes_msteams_width() -> None:
    payload = build_simple_card_payload(
        title="Title",
        message="Message",
        adaptive_card_version="1.2",
        full_width=True,
    )

    content = _card_content(payload)
    assert content["msteams"]["width"] == "Full"


def test_full_width_false_omits_msteams() -> None:
    payload = build_simple_card_payload(
        title="Title",
        message="Message",
        adaptive_card_version="1.2",
        full_width=False,
    )

    content = _card_content(payload)
    assert "msteams" not in content


def test_severity_warning_maps_to_warning_color() -> None:
    payload = build_rich_card_payload(
        title="Garage Door",
        message="Garage has been open for 20 minutes.",
        subtitle=None,
        severity="warning",
        facts=None,
        actions=None,
        adaptive_card_version="1.2",
        full_width=True,
    )

    content = _card_content(payload)
    assert content["body"][0]["color"] == "Warning"


def test_facts_render_as_factset() -> None:
    payload = build_rich_card_payload(
        title="Garage Door",
        message="Garage has been open for 20 minutes.",
        subtitle=None,
        severity="default",
        facts=[
            {"title": "Entity", "value": "cover.garage_door"},
            {"title": "Time", "value": "10:42 PM"},
        ],
        actions=None,
        adaptive_card_version="1.2",
        full_width=True,
    )

    content = _card_content(payload)
    factset = content["body"][-1]
    assert factset["type"] == "FactSet"
    assert factset["facts"][0]["title"] == "Entity"
    assert factset["facts"][0]["value"] == "cover.garage_door"


def test_open_url_actions_render_correctly() -> None:
    payload = build_rich_card_payload(
        title="Garage Door",
        message="Garage has been open for 20 minutes.",
        subtitle=None,
        severity="default",
        facts=None,
        actions=[
            {
                "title": "Open Home Assistant",
                "url": "https://ha.example.com/lovelace/security",
            }
        ],
        adaptive_card_version="1.2",
        full_width=True,
    )

    content = _card_content(payload)
    assert content["actions"][0]["type"] == "Action.OpenUrl"
    assert content["actions"][0]["title"] == "Open Home Assistant"
    assert content["actions"][0]["url"] == "https://ha.example.com/lovelace/security"


def test_empty_optional_fields_do_not_create_broken_card_json() -> None:
    payload = build_rich_card_payload(
        title="",
        message="System status nominal.",
        subtitle="",
        severity="default",
        facts=[{"title": "", "value": "ignored"}],
        actions=[{"title": "", "url": "https://example.com"}],
        adaptive_card_version="1.2",
        full_width=False,
    )

    content = _card_content(payload)
    assert len(content["body"]) == 1
    assert content["body"][0]["text"] == "System status nominal."
    assert "actions" not in content
