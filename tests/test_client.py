"""Tests for the Power Automate webhook client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientConnectionError, ClientError

from custom_components.teams_workflow_notify.client import (
    TeamsWorkflowNotifyClient,
    redact_url,
    validate_http_url,
    validate_image_url,
    validate_webhook_url,
)
from custom_components.teams_workflow_notify.const import MAX_PAYLOAD_SIZE_BYTES
from custom_components.teams_workflow_notify.exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowPayloadTooLargeError,
    TeamsWorkflowResponseError,
)

WEBHOOK_URL = "https://example.logic.azure.com/workflows/secret?sig=token"


def _session_with_response(status: int = 200) -> tuple[MagicMock, AsyncMock]:
    """Return a mocked session and response context manager."""
    session = MagicMock()
    response = AsyncMock()
    response.status = status
    response.read = AsyncMock(return_value=b"")
    request_context = MagicMock()
    request_context.__aenter__ = AsyncMock(return_value=response)
    request_context.__aexit__ = AsyncMock(return_value=None)
    session.post.return_value = request_context
    return session, response


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a URL",
        "ftp://example.com/hook",
        "https:///missing-host",
        "https://user:password@example.com/hook",
        "https://[invalid/hook",
    ],
)
def test_validate_http_url_rejects_unsafe_values(url: str) -> None:
    """General card action URLs should be absolute and credential-free."""
    with pytest.raises(ValueError):
        validate_http_url(url)


def test_validate_http_url_accepts_http_action() -> None:
    """Open-link actions may use an absolute local HTTP URL."""
    assert validate_http_url(" http://ha.local/dashboard#view ") == (
        "http://ha.local/dashboard#view"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "https://example.com/hook#fragment",
        "https://user@example.com/hook",
    ],
)
def test_validate_webhook_url_requires_secure_secret_url(url: str) -> None:
    """Workflow URLs must use HTTPS without fragments or credentials."""
    with pytest.raises(ValueError):
        validate_webhook_url(url)


def test_validate_and_redact_webhook_url() -> None:
    """The query token should never appear in a redacted URL."""
    assert validate_webhook_url(f" {WEBHOOK_URL} ") == WEBHOOK_URL
    assert redact_url(WEBHOOK_URL) == "https://example.logic.azure.com/[redacted]"
    assert redact_url("not a url") == "https://unknown-host/[redacted]"
    assert redact_url("https://[invalid") == "[redacted invalid url]"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            " https://cdn.example.com/image.png ",
            "https://cdn.example.com/image.png",
        ),
        (
            "data:image/png;base64,iVBORw0KGgo=",
            "data:image/png;base64,iVBORw0KGgo=",
        ),
        ("data:image/jpeg;base64,/9j/", "data:image/jpeg;base64,/9j/"),
        ("data:image/gif;base64,R0lGODdh", "data:image/gif;base64,R0lGODdh"),
        (" /local/camera image.png?cache=1 ", "/local/camera%20image.png?cache=1"),
        ("/config/www/camera.png", "/config/www/camera.png"),
        (
            "http://homeassistant.local:8123/local/camera.png",
            "http://homeassistant.local:8123/local/camera.png",
        ),
    ],
)
def test_validate_image_url_accepts_supported_sources(
    source: str, expected: str
) -> None:
    """Images may use public HTTPS URLs or inline Base64 data URIs."""
    assert validate_image_url(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "http://example.com/image.png",
        "https://example.com/image.png#fragment",
        "/local/image.png#fragment",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "data:image/png;base64,not-base64!",
        "data:image/png;base64,R0lGODdh",
        "data:image/png;base64,",
    ],
)
def test_validate_image_url_rejects_unsupported_sources(source: str) -> None:
    """Unsafe URLs and unsupported inline formats should be rejected."""
    with pytest.raises(ValueError):
        validate_image_url(source)


def test_validate_image_url_rejects_oversized_inline_image() -> None:
    """Inline images that cannot fit in a Teams message should fail early."""
    source = "data:image/png;base64," + "A" * MAX_PAYLOAD_SIZE_BYTES
    with pytest.raises(ValueError, match="message-size limit"):
        validate_image_url(source)


@pytest.mark.asyncio
async def test_send_payload_uses_exact_json_body_and_no_redirects() -> None:
    """The request should use a measured UTF-8 body and reject redirects."""
    session, response = _session_with_response()
    client = TeamsWorkflowNotifyClient(WEBHOOK_URL, session)

    await client.async_send_payload({"message": "café"})

    response.read.assert_not_awaited()
    call = session.post.call_args
    assert call.args == (WEBHOOK_URL,)
    assert call.kwargs["data"] == b'{"message":"caf\xc3\xa9"}'
    assert call.kwargs["headers"] == {
        "Content-Type": "application/json",
        "Connection": "close",
    }
    assert call.kwargs["allow_redirects"] is False
    assert call.kwargs["timeout"].total == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_send_payload_translates_auth_status(status: int) -> None:
    """Authorization failures should be distinguishable for reauthentication."""
    session, _ = _session_with_response(status)
    client = TeamsWorkflowNotifyClient(WEBHOOK_URL, session)

    with pytest.raises(TeamsWorkflowAuthError) as error:
        await client.async_send_payload({"message": "hello"})

    assert error.value.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [300, 400, 404, 429, 500])
async def test_send_payload_translates_other_status(status: int) -> None:
    """Redirects and unsuccessful responses should include only their status."""
    session, _ = _session_with_response(status)
    client = TeamsWorkflowNotifyClient(WEBHOOK_URL, session)

    with pytest.raises(TeamsWorkflowResponseError) as error:
        await client.async_send_payload({"message": "hello"})

    assert error.value.status == status


@pytest.mark.asyncio
async def test_send_payload_rejects_oversize_body_before_post() -> None:
    """Oversize JSON should not be sent to the Teams connector."""
    session, _ = _session_with_response()
    client = TeamsWorkflowNotifyClient(WEBHOOK_URL, session)

    with pytest.raises(TeamsWorkflowPayloadTooLargeError) as error:
        await client.async_send_payload({"message": "x" * MAX_PAYLOAD_SIZE_BYTES})

    assert error.value.size > error.value.limit
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_payload_rejects_unserializable_body() -> None:
    """Serialization failures should be integration errors and not send requests."""
    session, _ = _session_with_response()
    client = TeamsWorkflowNotifyClient(WEBHOOK_URL, session)

    with pytest.raises(TeamsWorkflowNotifyError, match="serialization"):
        await client.async_send_payload({"invalid": {object()}})

    session.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        (TimeoutError(), "timeout"),
        (ClientConnectionError("secret-safe test"), "ClientConnectionError"),
        (ClientError("secret-safe test"), "ClientError"),
    ],
)
async def test_send_payload_translates_connection_errors(
    exception: Exception, reason: str
) -> None:
    """Network failures should be normalized without exposing request details."""
    session = MagicMock()
    session.post.side_effect = exception
    client = TeamsWorkflowNotifyClient(WEBHOOK_URL, session)

    with pytest.raises(TeamsWorkflowConnectionError) as error:
        await client.async_send_payload({"message": "hello"})

    assert error.value.reason == reason
