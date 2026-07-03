# Microsoft Teams Workflow Notify

`Microsoft Teams Workflow Notify` is a Home Assistant custom integration that sends Microsoft Teams Adaptive Card notifications through a Power Automate webhook workflow.

It adds a real Home Assistant `notify` entity for normal notifications and a custom action for richer cards with facts, severity styling, and links.

## Why This Integration Exists

Traditional Microsoft Teams incoming webhooks and connectors are no longer the right fit for many setups. This integration uses a Power Automate workflow instead.

Home Assistant sends a Teams-style webhook payload to Power Automate, and Power Automate posts the Adaptive Card into Microsoft Teams as the Flow bot.

## Features

- UI-based setup through `Settings` -> `Devices & services`
- A real Home Assistant notify entity such as `notify.teams_workflow`
- Support for `notify.send_message`
- A custom `teams_workflow_notify.send_card` action for richer Adaptive Cards
- Editable webhook URL and card defaults through integration options
- Configurable card title, Adaptive Card version, and full-width layout
- Optional webhook verification during setup
- HACS-ready repository structure

## Power Automate Requirements

This integration assumes the Power Automate flow uses:

1. `When a Teams webhook request is received`
2. `Post your own adaptive card as the Flow bot to a channel`

The flow is expected to accept a Teams-compatible JSON payload with:

- top-level `"type": "message"`
- top-level `"attachments"`
- attachment `"contentType": "application/vnd.microsoft.card.adaptive"`
- attachment `"content"` containing the Adaptive Card JSON

One Home Assistant config entry sends to one Power Automate webhook URL.

## Installation

### Install with HACS

1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open the menu and select `Custom repositories`.
4. Add this repository:
   `https://github.com/CU-Jon/ha-teams-workflow-notify`
5. Select category `Integration`.
6. Install `Microsoft Teams Workflow Notify`.
7. Restart Home Assistant.

### Manual Installation

1. Download this repository.
2. Copy `custom_components/teams_workflow_notify` into the `custom_components` folder inside your Home Assistant configuration directory.
3. Restart Home Assistant.

The resulting path should look like:

```text
config/custom_components/teams_workflow_notify/
```

## Configuration

After restarting Home Assistant:

1. Go to `Settings` -> `Devices & services`.
2. Select `Add integration`.
3. Search for `Microsoft Teams Workflow Notify`.
4. Enter the Power Automate webhook URL.
5. Optionally adjust the initial defaults:
   - Notify entity name
   - Default card title
   - Adaptive Card version
   - Full-width Teams cards
   - Verify webhook during setup

If verification is enabled, Home Assistant sends a small test Adaptive Card before saving the integration.

After setup, the integration options can also be used to change the webhook URL later.

## Standard Notification Example

Use the normal Home Assistant notify action:

```yaml
action: notify.send_message
target:
  entity_id: notify.teams_workflow
data:
  title: "Garage Door"
  message: "Garage has been open for 20 minutes."
```

This sends a simple Adaptive Card to the configured Teams workflow.

## Rich Card Example

Use the custom action for a richer card:

```yaml
action: teams_workflow_notify.send_card
target:
  entity_id: notify.teams_workflow
data:
  title: "Garage Door"
  message: "Garage has been open for 20 minutes."
  subtitle: "Home Assistant"
  severity: "warning"
  facts:
    - title: "Entity"
      value: "cover.garage_door"
    - title: "Time"
      value: "10:42 PM"
  actions:
    - title: "Open Home Assistant"
      url: "https://ha.example.com/lovelace/security"
```

Supported severity values:

- `default`
- `info`
- `success`
- `warning`
- `error`

If only one integration entry exists, the custom action can be called without a target. If multiple entries exist, specify `target.entity_id`.

## Security

The Power Automate webhook URL is a secret.

- Do not share it publicly.
- Do not store it in public repositories.
- Do not include it in screenshots or logs.
- This integration stores the URL in the config entry and avoids logging the full value.

## Troubleshooting

### The integration cannot verify the webhook

- Make sure the Power Automate flow is turned on.
- Confirm the webhook URL was copied completely.
- Confirm the trigger is `When a Teams webhook request is received`.
- Disable verification temporarily if initial setup needs to proceed before testing.

### Notifications do not appear in Teams

- Check the Power Automate run history.
- Confirm the flow reaches `Post your own adaptive card as the Flow bot to a channel`.
- Confirm the flow is posting to the intended Team and channel.

### Home Assistant reports send errors

- `401` or `403` usually means the webhook is invalid or no longer authorized.
- `4xx` or `5xx` responses usually mean the flow rejected the request or failed internally.
- Connection errors or timeouts usually mean Home Assistant could not reach the webhook endpoint.

### The entity ID is different than expected

The default entity name is `Teams Workflow`, which usually becomes something like `notify.teams_workflow`. If the entity name is changed later, Home Assistant may keep the existing entity ID unless it is renamed in the entity registry.

## Known Limitations

- The Power Automate flow controls the final Teams destination
- Adaptive Card rendering can vary between Teams clients
- Each config entry supports one webhook URL

## Interactive Actions

This integration supports `Action.OpenUrl` buttons in rich cards.

`Action.Submit` is not omitted because the integration is unfinished. It is excluded because this integration uses a one-way webhook delivery model:

- Home Assistant sends a payload to Power Automate
- Power Automate posts the card into Teams
- There is no return channel from the posted card back into Home Assistant

Interactive submit actions require a two-way app or bot flow that can receive the user response after the card is rendered in Teams. That is a different architecture than a notify integration posting through a webhook workflow.

## Development Notes

Card builder tests are included in `tests/test_card.py`.

If a local Python environment with `pytest` is available, they can be run with:

```bash
python -m pytest tests/test_card.py
```
