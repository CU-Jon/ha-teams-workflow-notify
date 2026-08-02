"""Tests for the Adaptive Card builders."""

from __future__ import annotations

import pytest

from custom_components.teams_workflow_notify.card import (
    build_rich_card_payload,
    build_simple_card_payload,
)


def _card_content(payload: dict) -> dict:
    return payload["attachments"][0]["content"]


def test_simple_card_includes_title_and_message() -> None:
    """A simple notification should produce a valid Teams envelope."""
    payload = build_simple_card_payload(
        title=" Garage Door ",
        message=" Garage has been open for 20 minutes. ",
        full_width=True,
    )

    content = _card_content(payload)
    assert payload["type"] == "message"
    assert payload["attachments"][0]["contentType"] == (
        "application/vnd.microsoft.card.adaptive"
    )
    assert payload["attachments"][0]["contentUrl"] is None
    assert content["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"
    assert content["version"] == "1.2"
    assert content["body"][0]["text"] == "Garage Door"
    assert content["body"][0]["weight"] == "bolder"
    assert content["body"][0]["size"] == "medium"
    assert content["body"][1]["text"] == "Garage has been open for 20 minutes."
    assert content["msteams"]["width"] == "Full"


def test_simple_card_without_title() -> None:
    """A blank title should be omitted."""
    payload = build_simple_card_payload(
        title="  ",
        message="Message",
        full_width=False,
    )

    content = _card_content(payload)
    assert content["body"] == [{"type": "TextBlock", "text": "Message", "wrap": True}]
    assert "msteams" not in content


@pytest.mark.parametrize("message", ["", "   "])
def test_simple_card_rejects_empty_message(message: str) -> None:
    """Empty messages should fail before a webhook request is made."""
    with pytest.raises(ValueError, match="must not be empty"):
        build_simple_card_payload(
            title="Title",
            message=message,
            full_width=True,
        )


@pytest.mark.parametrize(
    ("severity", "expected_color"),
    [
        ("default", None),
        ("info", "accent"),
        ("success", "good"),
        ("warning", "warning"),
        ("error", "attention"),
    ],
)
def test_rich_card_severity(severity: str, expected_color: str | None) -> None:
    """Severity should map to the supported Adaptive Card color."""
    payload = build_rich_card_payload(
        title="Garage Door",
        message="Open",
        subtitle=None,
        severity=severity,
        facts=None,
        actions=None,
        full_width=True,
    )

    title = _card_content(payload)["body"][0]
    if expected_color is None:
        assert "color" not in title
    else:
        assert title["color"] == expected_color


def test_rich_card_includes_all_optional_content() -> None:
    """Subtitle, facts, and actions should use Teams-compatible casing."""
    payload = build_rich_card_payload(
        title="Garage Door",
        message="Garage has been open for 20 minutes.",
        subtitle=" Home Assistant ",
        severity="warning",
        facts=[
            {"title": " Entity ", "value": " cover.garage_door "},
            {"title": "Time", "value": "10:42 PM"},
        ],
        actions=[
            {
                "title": " Open Home Assistant ",
                "url": " https://ha.example.com/lovelace/security ",
            }
        ],
        full_width=True,
    )

    content = _card_content(payload)
    assert content["body"][0] == {
        "type": "TextBlock",
        "text": "Home Assistant",
        "isSubtle": True,
        "size": "small",
        "wrap": True,
        "spacing": "none",
    }
    factset = content["body"][-1]
    assert factset["type"] == "FactSet"
    assert factset["facts"][0] == {
        "title": "Entity",
        "value": "cover.garage_door",
    }
    assert content["actions"] == [
        {
            "type": "Action.OpenUrl",
            "title": "Open Home Assistant",
            "url": "https://ha.example.com/lovelace/security",
        }
    ]


def test_empty_optional_items_are_omitted() -> None:
    """Blank optional values should not produce malformed card elements."""
    payload = build_rich_card_payload(
        title="",
        message="System status nominal.",
        subtitle="",
        severity="default",
        facts=[
            {"title": "", "value": "ignored"},
            {"title": "Ignored", "value": ""},
        ],
        actions=[
            {"title": "", "url": "https://example.com"},
            {"title": "Ignored", "url": ""},
        ],
        full_width=False,
    )

    content = _card_content(payload)
    assert content["body"] == [
        {"type": "TextBlock", "text": "System status nominal.", "wrap": True}
    ]
    assert "actions" not in content


def test_rich_card_rejects_invalid_input() -> None:
    """The card builder should reject unsupported severity and empty messages."""
    with pytest.raises(ValueError, match="Unsupported severity"):
        build_rich_card_payload(
            title="Title",
            message="Message",
            subtitle=None,
            severity="critical",
            facts=None,
            actions=None,
            full_width=True,
        )

    with pytest.raises(ValueError, match="must not be empty"):
        build_rich_card_payload(
            title="Title",
            message=" ",
            subtitle=None,
            severity="default",
            facts=None,
            actions=None,
            full_width=True,
        )


def test_rich_card_includes_inline_image_with_accessible_fallback() -> None:
    """A Base64 image should remain inline and have useful alternative text."""
    payload = build_rich_card_payload(
        title="Front door",
        message="Motion detected",
        subtitle=None,
        severity="warning",
        facts=None,
        actions=None,
        full_width=True,
        image_url="data:image/png;base64,iVBORw0KGgo=",
    )

    image = _card_content(payload)["body"][-1]
    assert image == {
        "type": "Image",
        "url": "data:image/png;base64,iVBORw0KGgo=",
        "altText": "Front door",
        "size": "stretch",
    }


def test_rich_card_uses_explicit_image_alt_text() -> None:
    """Explicit image alternative text should override the title fallback."""
    payload = build_rich_card_payload(
        title="Front door",
        message="Motion detected",
        subtitle=None,
        severity="warning",
        facts=None,
        actions=None,
        full_width=True,
        image_url="https://cdn.example.com/front-door.jpg",
        image_alt_text="A person standing on the front porch",
    )

    assert _card_content(payload)["body"][-1]["altText"] == (
        "A person standing on the front porch"
    )
