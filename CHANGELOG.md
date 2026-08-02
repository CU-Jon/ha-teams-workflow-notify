# Changelog

All notable changes to this project are documented here.

## 1.0.0

- Add a native Home Assistant notify entity and rich Adaptive Card action.
- Fix every card to Adaptive Card schema 1.2 for Teams mobile compatibility.
- Support public HTTPS images and automatic URL-or-inline delivery of local images
  from Home Assistant's `www` directory, including metadata removal and adaptive
  resizing/compression for the Teams message budget.
- Validate and normalize supplied data URIs, automatically convert local files that
  exceed Teams' direct-image limits, and enforce Teams' six-action maximum.
- Add complete German, Spanish, French, Italian, Dutch, and Brazilian Portuguese
  translations, including translated action selector choices.
- Add UI setup, duplicate prevention, options, reconfiguration, and reauthentication.
- Add strict HTTPS validation, redacted diagnostics, redirect rejection, timeouts, and payload-size enforcement.
- Add HACS, Hassfest, lint, and test workflows.
- Add manifest-driven tag, release-branch, and GitHub release automation.
- Add Microsoft Teams branding from the pinned Home Assistant brands source.
