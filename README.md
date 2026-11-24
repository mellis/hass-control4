> **mellis fork:** includes security-partition zone sensors, House Alarm device grouping, and Night mode reporting fixes. See [installation and rollback instructions](TESTING.md).

# hass-control4

This custom integration for Home Assistant allows control of Control4 lights, locks (only locks that are relay-based in Control4), alarm control panels, door/window/motion sensors (as binary sensors), thermostats, fans, relay devices (as switches), and blinds/shades (as covers, stateless open/close/stop).

## Installation

First, add `https://github.com/mellis/hass-control4` as a [custom Integration repository](https://www.hacs.dev/docs/faq/custom_repositories/) in HACS.

Then, you can use the link below to install the integration through HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mellis&repository=hass-control4)

Once installed, follow the same setup instructions as the default integration: https://www.home-assistant.io/integrations/control4

### Additional configuration required for alarm control panel

If you are using an alarm control panel, you must go to Home Assistant -> Configuration -> Devices and Services -> Integrations and click "Configure" on the Control4 entry.

In the dialog that appears, choose the Control4 alarm arming modes that you want to correspond to each Home Assistant arming mode. For example, a DSC alarm system uses "Stay" as the "Alarm arm home mode name", and "Away" as the "Alarm arm away mode name". If your alarm system does not use one of the mode names, select `(not set)`. Once you click submit on the dialog, Home Assistant will be able to arm your alarm control panel and detect its state.

## Disclaimer

This fork extends lawtancool/hass-control4. It keeps the `control4` integration domain and existing entity identities.

This means, however, that this custom integration may not be as stable as the default integration, as the code has not gone through Home Assistant's review process and contains the newest, bleeding-edge features.

This integration is not affiliated with or endorsed by Control4.

## Local startup during a Control4 cloud outage

After a successful connection, the integration saves its Director token in a
private, per-entry Home Assistant storage file. On restart it first validates an
unexpired saved token against the local controller and authenticates event
subscriptions. Local discovery and control can then start without cloud login;
cloud token refresh runs in the background. Controller cloud metadata is optional.
A failed cloud refresh or rejected replacement does not overwrite the saved token.

This does not extend the token's lifetime (normally about 24 hours). Once it
expires or the controller rejects it, cloud authentication is required. The first
startup after installing this feature also needs cloud authentication to obtain a
token to save. No existing token can be recovered after it has been lost from memory.

The cache contains a bearer credential. Home Assistant writes it using its private,
atomic storage API; it is not separately encrypted by this integration. Protect the
configuration directory and backups as credentials. The cache stores no account
password or cloud account token, is scoped to the configured host, account and
controller, and is deleted when the integration entry is removed. Unloading or
restarting the integration preserves it. To roll back, restore the previous
integration files and restart HA; the previous version ignores the cache.
