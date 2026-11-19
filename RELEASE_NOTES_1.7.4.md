# 1.7.4 — Recover from rejected token refreshes

Fixes an outage where Control4 entities could remain unavailable after the daily token refresh until the integration was manually reloaded.

The integration previously treated a WebSocket transport connection as a successful refresh. If the controller rejected the subsequent subscription request, that error ran in a background task after the integration had already scheduled its next refresh almost 24 hours later.

## Changes

- Wait for authenticated subscription setup before treating a token refresh as successful.
- Validate candidate tokens with a read-only controller request, and restore the previous REST client when subscription setup fails.
- Retry transient account, controller, and subscription failures with bounded backoff. Retry logs identify the failed stage and exception type without logging token values.
- Start Home Assistant's existing reauthentication flow for invalid account credentials during a scheduled refresh.
- Refresh short-lived tokens before expiry and keep retry delays bounded during long outages.
- Pin the matching pyControl4 fix to an immutable commit, installed automatically by Home Assistant.

## Installation

For the existing `mellis/hass-control4` HACS custom repository, select version **1.7.4** after this release is published, download it, and restart Home Assistant. A config-entry reload alone does not import the new Python code or install its updated dependency. Keep the existing Control4 integration entry and entities.

For manual installation, extract `control4-1.7.4.zip` into your Home Assistant config directory. It contains `custom_components/control4/`. Restart Home Assistant afterward.

No entity IDs, integration configuration, or device commands change. The fix does not send alarm arming/disarming, lock, or light commands as part of token validation.

## Validation

- Python 3.14, Home Assistant 2026.10.2.
- pyControl4: 68 tests passed.
- Integration: 66 tests passed, including 15 token refresh regression cases.
- Live installation and a full daily refresh cycle have not yet been verified; the current Home Assistant installation was not modified.

## Rollback

Select **1.7.3** in HACS, download, and restart Home Assistant. Keep the existing integration entry. Version 1.7.3 remains susceptible to the token-refresh outage.
