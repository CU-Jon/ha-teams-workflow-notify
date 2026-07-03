"""Adaptive Card payload builders for Microsoft Teams Workflow Notify."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .const import (
    ATTR_ACTIONS,
    ATTR_ACTION_URL,
    ATTR_FACTS,
    ATTR_FACT_VALUE,
    SEVERITIES,
    SEVERITY_DEFAULT,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
)

_SCHEMA_URL = "http://adaptivecards.io/schemas/adaptive-card.json"
_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"

_SEVERITY_TO_COLOR: dict[str, str | None] = {
    SEVERITY_DEFAULT: None,
    SEVERITY_INFO: "accent",
    SEVERITY_SUCCESS: "good",
    SEVERITY_WARNING: "warning",
    SEVERITY_ERROR: "attention",
}


def _clean_text(value: str | None) -> str | None:
    """Return a trimmed string or None."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _base_card(adaptive_card_version: str, full_width: bool) -> dict[str, Any]:
    """Return the base Adaptive Card structure."""
    card: dict[str, Any] = {
        "$schema": _SCHEMA_URL,
        "type": "AdaptiveCard",
        "version": adaptive_card_version,
        "body": [],
    }
    if full_width:
        card["msteams"] = {"width": "Full"}
    return card


def _wrap_payload(card: dict[str, Any]) -> dict[str, Any]:
    """Wrap the Adaptive Card in the Teams webhook envelope."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": _CONTENT_TYPE,
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def build_simple_card_payload(
    *,
    title: str | None,
    message: str,
    adaptive_card_version: str,
    full_width: bool,
) -> dict[str, Any]:
    """Build a simple Adaptive Card payload."""
    message_text = _clean_text(message)
    if message_text is None:
        raise ValueError("Message must not be empty")

    card = _base_card(adaptive_card_version, full_width)
    body = card["body"]

    title_text = _clean_text(title)
    if title_text is not None:
        body.append(
            {
                "type": "TextBlock",
                "text": title_text,
                "weight": "bolder",
                "size": "medium",
                "wrap": True,
            }
        )

    body.append(
        {
            "type": "TextBlock",
            "text": message_text,
            "wrap": True,
        }
    )

    return _wrap_payload(card)


def build_rich_card_payload(
    *,
    title: str | None,
    message: str,
    subtitle: str | None,
    severity: str,
    facts: Iterable[dict[str, str]] | None,
    actions: Iterable[dict[str, str]] | None,
    adaptive_card_version: str,
    full_width: bool,
) -> dict[str, Any]:
    """Build a richer Adaptive Card payload."""
    if severity not in SEVERITIES:
        raise ValueError(f"Unsupported severity: {severity}")

    message_text = _clean_text(message)
    if message_text is None:
        raise ValueError("Message must not be empty")

    card = _base_card(adaptive_card_version, full_width)
    body = card["body"]

    subtitle_text = _clean_text(subtitle)
    if subtitle_text is not None:
        body.append(
            {
                "type": "TextBlock",
                "text": subtitle_text,
                "isSubtle": True,
                "size": "small",
                "wrap": True,
                "spacing": "None",
            }
        )

    title_text = _clean_text(title)
    if title_text is not None:
        title_block: dict[str, Any] = {
            "type": "TextBlock",
            "text": title_text,
            "weight": "bolder",
            "size": "medium",
            "wrap": True,
        }
        color = _SEVERITY_TO_COLOR[severity]
        if color is not None:
            title_block["color"] = color
        body.append(title_block)

    body.append(
        {
            "type": "TextBlock",
            "text": message_text,
            "wrap": True,
        }
    )

    fact_items = [
        {
            "title": title_value,
            ATTR_FACT_VALUE: value_value,
        }
        for fact in facts or []
        if (title_value := _clean_text(fact.get("title")))
        and (value_value := _clean_text(fact.get(ATTR_FACT_VALUE)))
    ]
    if fact_items:
        body.append({"type": "FactSet", ATTR_FACTS: fact_items})

    action_items = [
        {
            "type": "Action.OpenUrl",
            "title": title_value,
            ATTR_ACTION_URL: url_value,
        }
        for action in actions or []
        if (title_value := _clean_text(action.get("title")))
        and (url_value := _clean_text(action.get(ATTR_ACTION_URL)))
    ]
    if action_items:
        card[ATTR_ACTIONS] = action_items

    return _wrap_payload(card)
