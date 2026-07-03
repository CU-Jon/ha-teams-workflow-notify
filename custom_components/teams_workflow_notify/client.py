"""Webhook client for Microsoft Teams Workflow Notify."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientConnectionError, ClientError, ClientSession, ClientTimeout
from yarl import URL

from .const import REQUEST_TIMEOUT_SECONDS
from .exceptions import (
    TeamsWorkflowAuthError,
    TeamsWorkflowConnectionError,
    TeamsWorkflowNotifyError,
    TeamsWorkflowResponseError,
)

_LOGGER = logging.getLogger(__name__)


def validate_http_url(url: str) -> str:
    """Validate and normalize an absolute HTTP or HTTPS URL."""
    candidate = url.strip()
    try:
        parsed = URL(candidate)
    except Exception as err:
        raise ValueError("Invalid URL") from err

    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise ValueError("Webhook URL must use HTTP or HTTPS")

    return str(parsed)


def redact_url(url: str) -> str:
    """Return a redacted representation of a webhook URL."""
    try:
        parsed = URL(url)
    except Exception:
        return "[redacted invalid url]"

    scheme = parsed.scheme or "https"
    host = parsed.host or "unknown-host"
    return f"{scheme}://{host}/[redacted]"


def _response_snippet(text: str) -> str:
    """Return a sanitized response snippet for logs and errors."""
    cleaned = " ".join(text.split())
    if len(cleaned) > 200:
        return f"{cleaned[:197]}..."
    return cleaned


class TeamsWorkflowNotifyClient:
    """Post Adaptive Card payloads to a Power Automate Teams webhook."""

    def __init__(self, webhook_url: str, session: ClientSession) -> None:
        """Initialize the client."""
        self._webhook_url = validate_http_url(webhook_url)
        self._session = session
        self._redacted_url = redact_url(self._webhook_url)

    async def async_send_payload(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload to the configured webhook."""
        timeout = ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

        try:
            async with self._session.post(
                self._webhook_url,
                json=payload,
                headers={"Content-Type": "application/json", "Connection": "close"},
                timeout=timeout,
            ) as response:
                response_text = await response.text()
        except asyncio.TimeoutError as err:
            raise TeamsWorkflowConnectionError(
                f"Timed out contacting webhook at {self._redacted_url}"
            ) from err
        except ClientConnectionError as err:
            _LOGGER.warning(
                "Connection error sending webhook to %s: %s: %s",
                self._redacted_url,
                err.__class__.__name__,
                err,
            )
            raise TeamsWorkflowConnectionError(
                f"Could not connect to webhook at {self._redacted_url} ({err.__class__.__name__}: {err})"
            ) from err
        except ClientError as err:
            _LOGGER.warning(
                "HTTP client error sending webhook to %s: %s: %s",
                self._redacted_url,
                err.__class__.__name__,
                err,
            )
            raise TeamsWorkflowConnectionError(
                f"Webhook request failed for {self._redacted_url}: {err.__class__.__name__}: {err}"
            ) from err
        except ValueError as err:
            raise TeamsWorkflowNotifyError("Payload serialization failed") from err

        if 200 <= response.status < 300:
            _LOGGER.debug(
                "Webhook request succeeded for %s with status %s",
                self._redacted_url,
                response.status,
            )
            return

        snippet = _response_snippet(response_text) or "empty response body"
        if response.status in (401, 403):
            raise TeamsWorkflowAuthError(
                f"Webhook rejected the request with status {response.status}: {snippet}"
            )

        raise TeamsWorkflowResponseError(
            f"Webhook returned status {response.status}: {snippet}"
        )
