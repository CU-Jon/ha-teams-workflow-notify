# Microsoft Teams Workflow Notify

[![HACS validation](https://github.com/CU-Jon/ha-teams-workflow-notify/actions/workflows/hacs.yaml/badge.svg)](https://github.com/CU-Jon/ha-teams-workflow-notify/actions/workflows/hacs.yaml)
[![Hassfest](https://github.com/CU-Jon/ha-teams-workflow-notify/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/CU-Jon/ha-teams-workflow-notify/actions/workflows/hassfest.yaml)
[![Tests](https://github.com/CU-Jon/ha-teams-workflow-notify/actions/workflows/tests.yaml/badge.svg)](https://github.com/CU-Jon/ha-teams-workflow-notify/actions/workflows/tests.yaml)

Microsoft Teams Workflow Notify is a Home Assistant custom integration that sends Adaptive Card notifications to a Teams channel through a Microsoft Power Automate/Teams Workflows webhook.

It provides a native `notify` entity for normal notifications and a `teams_workflow_notify.send_card` action for cards with subtitles, severity styling, facts, images, and open-link buttons.

All cards use Adaptive Card schema version 1.2. This is intentionally fixed because Microsoft recommends version 1.2 for consistent rendering in Teams mobile clients.

## Requirements

- Home Assistant 2026.7.0 or newer
- Permission to create and own a workflow for the destination Teams channel
- A workflow based on the Teams **When a Teams webhook request is received** trigger

Each integration entry represents one workflow URL and therefore one workflow-controlled Teams destination.

## Create the Teams workflow

The simplest supported setup uses Microsoft's current **Send webhook alerts to a channel** workflow template:

1. In Microsoft Teams, open the destination channel's menu and select **Workflows**.
2. Find **Send webhook alerts to a channel**, then follow the prompts to select the Team and channel.
3. For **Who can trigger the flow?**, select **Anyone**. This integration does not send a Microsoft Entra access token.
4. Save the workflow and copy its HTTPS webhook URL.
5. Keep at least one valid owner on the workflow. Adding a co-owner avoids losing access if the original owner leaves.

The URL is created only after the workflow is saved. Treat it as a password: anyone who has it can invoke a workflow configured for anonymous access.

Do not use the retired **Post your own adaptive card as the Flow bot to a channel** action. If you build the workflow manually, use the current **Post card in a chat or channel** action and preserve the Teams webhook message envelope expected by the template.

## Installation

### HACS custom repository

[![Open your Home Assistant instance and add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=CU-Jon&repository=ha-teams-workflow-notify&category=integration)

Until the repository is accepted into the HACS default list:

1. In HACS, open **Integrations** and select **Custom repositories** from the menu.
2. Add `https://github.com/CU-Jon/ha-teams-workflow-notify` as an **Integration** repository.
3. Install **Microsoft Teams Workflow Notify**.
4. Restart Home Assistant.

### Manual installation

Copy `custom_components/teams_workflow_notify` into the `custom_components` directory in your Home Assistant configuration, then restart Home Assistant. The resulting path must be:

```text
<config>/custom_components/teams_workflow_notify/
```

## Configuration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Microsoft Teams Workflow Notify**.
3. Enter the workflow's HTTPS URL and choose the card defaults.
4. Submit the form. Home Assistant sends one visible verification card before it saves the entry.

Use **Configure** to change the connection name or card defaults. Use the integration entry's **Reconfigure** action to replace the secret webhook URL; replacement URLs are also verified before saving.

The integration prevents duplicate entries for the same normalized webhook URL. A `401` or `403` response starts Home Assistant's reauthentication flow.

## Standard notification

Use Home Assistant's native notify action:

```yaml
action: notify.send_message
target:
  entity_id: notify.teams_workflow
data:
  title: "Garage Door"
  message: "Garage has been open for 20 minutes."
```

## Rich Adaptive Card

The custom action requires an explicit notify-entity target:

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
  image_url: "/local/snapshots/garage-door.jpg"
  image_delivery: "auto"
  image_alt_text: "The open garage door"
```

Supported severity values are `default`, `info`, `success`, `warning`, and `error`.

Facts must be a list of objects containing non-empty `title` and `value` strings. Actions must be a list of no more than six objects containing a non-empty `title` and an absolute HTTP or HTTPS `url`.

### Images

The rich-card action supports one optional PNG, JPEG, or GIF image. `image_url` accepts:

- A local URL below `/local/`, such as `/local/snapshots/front-door.jpg`. This maps to `/config/www/snapshots/front-door.jpg` on Home Assistant OS.
- An absolute file path inside Home Assistant's configured `www` directory, such as `/config/www/snapshots/front-door.jpg` on Home Assistant OS.
- A public, direct HTTPS image URL. Microsoft Teams must be able to retrieve it without authentication or redirects.
- A Base64 data URI such as `data:image/jpeg;base64,<encoded image>`.

`image_delivery` controls how a local image is sent:

- `auto` (default): if Home Assistant has a configured external HTTPS URL or an active Home Assistant Cloud URL and the local file already meets Teams' direct-image limits, the integration sends that origin plus the image's `/local/...` path. Otherwise, it embeds an optimized Base64 copy in the card.
- `url`: require an external HTTPS or cloud URL and a static local PNG, JPEG, or GIF no larger than 1 MB or 1024 × 1024 pixels. The action fails instead of silently changing delivery when either requirement is not met.
- `inline`: always normalize and embed the local file or supplied data URI, even when Home Assistant is externally accessible.

In practice, the same `image_url: /local/snapshots/front-door.jpg` and default `auto` setting covers both installations. On an externally accessible instance, a compatible image becomes a URL such as `https://ha.example.com/local/snapshots/front-door.jpg`; on a private-only instance—or when the source needs resizing, format normalization, animation removal, or size reduction—it becomes a `data:image/...;base64,...` value inside the card payload. The file must already exist before `send_card` runs. If an automation repeatedly replaces the same externally served file, add a changing query value or use unique filenames to avoid a cached image.

Public HTTPS sources remain URLs in `auto` and `url` mode. The integration deliberately does not download remote images; therefore, `inline` can be used only with a local `www` file or an already encoded data URI.

For inline delivery, the integration reads only files whose resolved path remains inside `www`, including after symbolic links are resolved. It accepts source files up to 10 MB and 20 megapixels, fully validates local files and supplied data URIs, applies EXIF orientation, removes metadata, uses only the first frame of a GIF, caps the image at 1024 × 1024 pixels, and progressively resizes and compresses it to fit the remaining card budget. If it still cannot fit, the action fails before contacting the workflow. A 1 KB safety margin is reserved because Microsoft describes the connector's 28 KB message limit as approximate.

Use `image_alt_text` to provide an accessible description. If it is omitted, the card title is used. Images are supported only by `teams_workflow_notify.send_card`, not the standard `notify.send_message` action.

The external URL selected by Home Assistant must actually be reachable by Microsoft Teams, and `/local` files served this way are unauthenticated public content. Do not place sensitive images in `www` when external access is enabled. If that is unsuitable, choose `inline`; the image is then contained in the webhook request instead of being published at a retrievable URL.

Microsoft limits card images to static PNG, JPEG, or GIF files no larger than 1 MB or 1024 × 1024 pixels; animated GIFs and SVG are not supported. A direct public HTTPS image URL must already meet those requirements. The integration verifies local URL sources and automatically converts them in `auto` mode when needed, but deliberately does not download or inspect third-party URLs.

## Translations

The integration includes complete English, German, Spanish, French, Italian, Dutch, and Brazilian Portuguese translations for setup, options, action fields, selector choices, and runtime errors.

## Security and privacy

- The webhook URL is stored in Home Assistant's config-entry storage and is never logged in full.
- Diagnostics redact the webhook URL.
- Response bodies are neither retained nor logged because a workflow could echo sensitive input.
- Redirects are rejected so the secret URL is not forwarded to another host.
- Only HTTPS is accepted for the workflow URL.
- Local image paths are restricted to Home Assistant's `www` directory; arbitrary local files and remote image downloads are rejected.

If a URL is exposed, regenerate it in Power Automate and use **Reconfigure** in Home Assistant.

## Limits and delivery behavior

- Microsoft documents an approximate 28 KB message-size limit for the Teams connector. This integration measures the exact UTF-8 JSON body and rejects oversized cards before sending.
- Requests are not automatically retried. A POST may have reached the workflow even when the response was lost, so retrying could create duplicate channel messages.
- `Action.OpenUrl` buttons are supported. `Action.Submit` is not supported because this one-way notification integration has no callback channel from Teams to Home Assistant.
- Adaptive Card schema version 1.2 is hardcoded for maximum compatibility with Teams desktop, web, and mobile clients.

## Troubleshooting

If setup verification fails:

- Confirm the workflow is enabled and has been saved.
- Confirm the trigger is **When a Teams webhook request is received** and its authentication setting is **Anyone**.
- Copy the complete, current URL again; old URLs can stop working after a workflow is changed or regenerated.
- Check the Power Automate run history. A run that started but failed indicates a workflow/action problem; no run usually indicates a URL, authentication, or connectivity problem.

If Home Assistant reports an HTTP error, inspect the matching workflow run. For `401` or `403`, complete the repair flow Home Assistant creates or use **Reconfigure** with a current URL.

To share diagnostics, open the integration entry and select **Download diagnostics**. The secret webhook URL is redacted, but review any file before posting it publicly.

## Removal

Remove the integration entry from **Settings → Devices & services**. Then remove the repository in HACS if it is no longer needed and restart Home Assistant. Removing this integration does not delete the Power Automate workflow; delete or disable that workflow separately if appropriate.

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the local checks expected before a pull request. Security-sensitive reports should follow [SECURITY.md](SECURITY.md).

## License

This project is licensed under the MIT License.
