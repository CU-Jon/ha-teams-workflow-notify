"""Webhook client for Microsoft Teams Workflow Notify."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import ClientConnectionError, ClientError, ClientSession, ClientTimeout
from yarl import URL

from .const import MAX_PAYLOAD_SIZE_BYTES, REQUEST_TIMEOUT_SECONDS
from .exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowPayloadTooLargeError,
    TeamsWorkflowResponseError,
)

_LOGGER = logging.getLogger(__name__)


def validate_http_url(url: str) -> str:
    """Validate and normalize an absolute HTTP or HTTPS URL."""
    candidate = url.strip()
    try:
        parsed = URL(candidate)
        host = parsed.host
        _ = parsed.port
        user = parsed.user
        password = parsed.password
    except Exception as err:
        raise ValueError("Invalid URL") from err

    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or user is not None
        or password is not None
    ):
        raise ValueError("Webhook URL must use HTTP or HTTPS")

    return str(parsed)


def validate_webhook_url(url: str) -> str:
    """Validate and normalize a secure Power Automate webhook URL."""
    normalized = validate_http_url(url)
    parsed = URL(normalized)
    if parsed.scheme != "https" or parsed.fragment:
        raise ValueError("Webhook URL must use HTTPS and must not contain a fragment")
    return normalized


def validate_image_url(url: str) -> str:
    """Validate a supported public, inline, or local image source."""
    candidate = url.strip()
    if candidate.startswith("data:"):
        if len(candidate.encode()) > MAX_PAYLOAD_SIZE_BYTES:
            raise ValueError("Inline image exceeds the Teams message-size limit")

        header, separator, encoded = candidate.partition(",")
        if (
            header
            not in {
                "data:image/gif;base64",
                "data:image/jpeg;base64",
                "data:image/png;base64",
            }
            or not separator
            or not encoded
        ):
            raise ValueError("Unsupported inline image data URI")

        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as err:
            raise ValueError("Invalid Base64 image data") from err

        signatures = {
            "data:image/gif;base64": (b"GIF87a", b"GIF89a"),
            "data:image/jpeg;base64": (b"\xff\xd8\xff",),
            "data:image/png;base64": (b"\x89PNG\r\n\x1a\n",),
        }
        if not image_bytes.startswith(signatures[header]):
            raise ValueError("Inline image data does not match its media type")
        return candidate

    if candidate.startswith("/local/"):
        parsed = URL(candidate)
        if parsed.fragment:
            raise ValueError("Local image URL must not contain a fragment")
        return str(parsed)

    if Path(candidate).is_absolute() and "://" not in candidate:
        return candidate

    normalized = validate_http_url(candidate)
    parsed = URL(normalized)
    if parsed.fragment or (parsed.scheme != "https" and parsed.path[:7] != "/local/"):
        raise ValueError("Image URL must use HTTPS and must not contain a fragment")
    return normalized


def serialize_payload(payload: dict[str, Any]) -> bytes:
    """Serialize a payload exactly as it will be sent."""
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    except (TypeError, ValueError) as err:
        raise TeamsWorkflowNotifyError("Payload serialization failed") from err


def redact_url(url: str) -> str:
    """Return a redacted representation of a webhook URL."""
    try:
        parsed = URL(url)
    except Exception:
        return "[redacted invalid url]"

    scheme = parsed.scheme or "https"
    host = parsed.host or "unknown-host"
    return f"{scheme}://{host}/[redacted]"


class TeamsWorkflowNotifyClient:
    """Post Adaptive Card payloads to a Power Automate Teams webhook."""

    def __init__(self, webhook_url: str, session: ClientSession) -> None:
        """Initialize the client."""
        self._webhook_url = validate_webhook_url(webhook_url)
        self._session = session
        self._redacted_url = redact_url(self._webhook_url)

    async def async_send_payload(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload to the configured webhook."""
        timeout = ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

        body = serialize_payload(payload)

        if (payload_size := len(body)) > MAX_PAYLOAD_SIZE_BYTES:
            raise TeamsWorkflowPayloadTooLargeError(
                payload_size, MAX_PAYLOAD_SIZE_BYTES
            )

        try:
            async with self._session.post(
                self._webhook_url,
                data=body,
                headers={"Content-Type": "application/json", "Connection": "close"},
                timeout=timeout,
                allow_redirects=False,
            ) as response:
                response_status = response.status
        except TimeoutError as err:
            raise TeamsWorkflowConnectionError("timeout") from err
        except ClientConnectionError as err:
            _LOGGER.warning(
                "Connection error sending webhook to %s (%s)",
                self._redacted_url,
                err.__class__.__name__,
            )
            raise TeamsWorkflowConnectionError(err.__class__.__name__) from err
        except ClientError as err:
            _LOGGER.warning(
                "HTTP client error sending webhook to %s (%s)",
                self._redacted_url,
                err.__class__.__name__,
            )
            raise TeamsWorkflowConnectionError(err.__class__.__name__) from err

        if 200 <= response_status < 300:
            _LOGGER.debug(
                "Webhook request succeeded for %s with status %s",
                self._redacted_url,
                response_status,
            )
            return

        if response_status in (401, 403):
            raise TeamsWorkflowAuthError(response_status)

        raise TeamsWorkflowResponseError(response_status)
