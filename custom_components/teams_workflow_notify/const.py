"""Constants for Microsoft Teams Workflow Notify."""

from __future__ import annotations

DOMAIN = "teams_workflow_notify"
PLATFORMS: list[str] = ["notify"]

CONF_WEBHOOK_URL = "webhook_url"
CONF_ENTITY_NAME = "entity_name"
CONF_DEFAULT_CARD_TITLE = "default_card_title"
CONF_ADAPTIVE_CARD_VERSION = "adaptive_card_version"
CONF_FULL_WIDTH = "full_width"
CONF_VERIFY_WEBHOOK = "verify_webhook"

DEFAULT_ENTITY_NAME = "Teams Workflow"
DEFAULT_CARD_TITLE = "Home Assistant"
DEFAULT_ADAPTIVE_CARD_VERSION = "1.2"
DEFAULT_FULL_WIDTH = True
DEFAULT_VERIFY_WEBHOOK = True
DEFAULT_VERIFICATION_TITLE = "Microsoft Teams Workflow Notify"
DEFAULT_VERIFICATION_MESSAGE = "Webhook verification from Home Assistant succeeded."

ADAPTIVE_CARD_VERSIONS: tuple[str, ...] = ("1.2", "1.3", "1.4", "1.5")

SERVICE_SEND_CARD = "send_card"

ATTR_SUBTITLE = "subtitle"
ATTR_SEVERITY = "severity"
ATTR_FACTS = "facts"
ATTR_ACTIONS = "actions"
ATTR_FACT_VALUE = "value"
ATTR_ACTION_URL = "url"

SEVERITY_DEFAULT = "default"
SEVERITY_INFO = "info"
SEVERITY_SUCCESS = "success"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
SEVERITIES: tuple[str, ...] = (
    SEVERITY_DEFAULT,
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
    SEVERITY_ERROR,
)

REQUEST_TIMEOUT_SECONDS = 10
