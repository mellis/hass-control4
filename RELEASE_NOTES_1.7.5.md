# 1.7.5 — Local startup during Control4 cloud outages

Home Assistant can now reuse a previously validated Director token after a restart, allowing local Control4 discovery and control to start while the Control4 cloud is unavailable, provided the saved token is still valid.

## Changes

- Persist the last token accepted by both the local read-only API and authenticated event subscriptions, together with its absolute expiry time.
- Validate saved tokens locally on startup and refresh them in the background. Missing, expired or rejected tokens fall back to cloud authentication.
- Preserve the saved credential when cloud refresh fails or returns a rejected replacement. Attempt to restore the previous event subscription if replacement authentication fails.
- Make cloud controller metadata optional and cache the software version so those cloud endpoints no longer block local startup.
- Scope the private token cache to the configured host, account and controller, and delete it when the integration entry is removed.

## Limitations and credential storage

The first successful connection after installing this release must obtain a token from the cloud to seed the cache. This cannot recover a token already lost before installation. Cached tokens retain their original expiry (normally about 24 hours); this feature does not extend validity or bypass revocation.

The cache uses Home Assistant's Store helper with owner-only file permissions. Tokens are not separately encrypted by the integration. Protect the configuration directory and backups as credentials. Failed refreshes do not overwrite the last validated token.

## Installation

In the existing `mellis/hass-control4` HACS custom repository, select **1.7.5** after publication, download it, and restart Home Assistant. A config-entry reload alone does not import the new Python code. Keep the existing integration entry and entities.

For manual installation, extract `control4-1.7.5.zip` into your Home Assistant config directory. It contains `custom_components/control4/`. Restart Home Assistant afterward.

The pinned pyControl4 dependency is unchanged from 1.7.4. Token validation sends read-only requests and establishes event subscriptions; it does not send light, lock or alarm control commands.

## Validation

- Python 3.14, Home Assistant 2026.10.2, and the manifest-pinned pyControl4 dependency.
- Integration: 100 tests passed, covering offline startup, cache expiry and identity isolation, rejected replacements, refresh recovery, disk failures, subscription restoration, and real Home Assistant storage persistence and private permissions.
- Python formatting and whitespace checks passed.
- No live deployment or physical device validation has been performed for this release.

## Rollback

Select **1.7.4** in HACS, download, and restart Home Assistant. Keep the existing integration entry. Version 1.7.4 ignores the cache and again requires cloud authentication on startup. The cache file remains on disk when rolling back; protect it along with the rest of the configuration directory.
