# Contributing

Thanks for helping improve Microsoft Teams Workflow Notify.

## Before opening an issue

- Search existing issues.
- Confirm the problem still occurs on a supported Home Assistant version and the latest integration release.
- Check the Power Automate run history and Home Assistant logs.
- Remove webhook URLs, access tokens, tenant details, and other secrets from all attachments.

## Development setup

Use Python 3.14 or newer, create a virtual environment, and install the test requirements:

```bash
python -m pip install -r requirements_test.txt
```

Run the same checks used by continuous integration:

```bash
ruff check .
ruff format --check .
pytest
```

Changes should include tests for new behavior. Keep the complete English user-facing text in `translations/en.json`, preserve the same keys and placeholders in every locale, and update the other translations when possible.

## Pull requests

- Keep each pull request focused on one problem.
- Explain the user-visible behavior and how it was tested.
- Update the README and changelog when behavior, setup, or compatibility changes.
- Do not include real workflow URLs in source, fixtures, logs, screenshots, or commit messages.

## Releases

Before merging a release, update `version` in `custom_components/teams_workflow_notify/manifest.json` using `X.X.X` format. A push to `main`, including the push created by merging a pull request, creates the matching `vX.X.X` tag, `release/vX.X.X` branch, and GitHub release. If that tag already exists, the workflow is idempotent and does not move it or publish a duplicate release.
