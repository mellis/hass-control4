# Alarm zone preview: 1.7.1b6

This preview adds passive binary sensors for zones belonging to security partitions,
including zones absent from Control4's standalone sensor item list. It revives
https://github.com/lawtancool/pyControl4/pull/57 using the original mobile-app
`GET_ZONE_LIST` API. `GET_SETUP` is a fallback for drivers without that command.
No arming, disarming, bypass, keypad, or alarm trigger commands are added or sent
by zone discovery and state tracking.

## Versions

- Based on integration 1.7.0 (not installed 1.6.0): this includes the intervening upstream changes.
- Requires Home Assistant 2026.10.2 for this tested preview.
- Installs pyControl4 2.0.3.dev1 from mellis/pyControl4, pinned to commit
  `156f1ca82c7338db7ace8a876a4b613ace538f3c` in the manifest. No manual pip installation on HA is needed.
- Local validation: library 61 tests; integration 32 tests against real Home Assistant
  2026.10.2 entity/coordinator APIs, with mocked Control4 responses.
- Live discovery was verified on a DSC TL-280 driver with Partition 1. The preview skips the parent securitypanel proxy when partition proxies exist, and skips disabled partitions. Door/window transition checks remain the user test.

## Install for a first test (manual, keeps existing integration configuration)

1. Copy the complete existing `/config/custom_components/control4` directory to
   `/config/control4-before-alarm-zones`. Keep the backup outside `custom_components`.
2. Download `control4-1.7.1b6.zip` from this fork's 1.7.1b6 prerelease.
   Extract it: it contains `custom_components/control4/`. Replace the installed
   directory with that directory. The resulting manifest must be at
   `/config/custom_components/control4/manifest.json`.
3. Restart Home Assistant so it imports the new code and installs the pinned dependency.
   A config-entry reload alone does not load replacement Python modules.
4. Keep your existing Control4 integration entry. Do not delete or recreate it.
   Avoid upstream HACS updates during the manual test: they would replace this code.

This package is also a normal HACS integration source release. To have HACS manage
the fork later, switch its repository from lawtancool/hass-control4 to
mellis/hass-control4 as a custom Integration repository and select the 1.7.1b6
prerelease (enable beta versions if hidden). Only one repository can own the
`control4` directory. Keep the Home Assistant config entry when changing HACS repositories.
The manual installation above avoids changing repository ownership for the first test.

Zone entities belong directly to the existing parent alarm hardware device,
alongside its alarm partition entities (for example, **House Alarm**). Device names
and hardware metadata are preserved. Grouping preserves existing entity IDs and
unique IDs. A partition without a parent hardware item gets its own fallback device.

## Test with Partition 1

1. In Settings > Devices & services > Entities, filter by the Control4 integration.
   Find the new door/window zone names. New sensor attributes contain
   `alarm_partition_id` (the Control4 item ID, not the label "1") and `alarm_zone_id`.
2. Confirm a closed contact displays Closed/Off and an open contact Open/On.
   Open and close one safe door or window and watch its state. Changes should appear
   immediately if the driver emits `OnDataToUI.zone_state`, or within about 30 seconds
   through the fallback polling. Verify another zone does not change along with it.
3. Restart Home Assistant and confirm initial zone states and entity IDs persist.
4. Check that existing Control4 lights, sensors and the alarm entity still work.
   This preview adds sensors; it does not change existing item-sensor unique IDs.

No alarm arming or fire/gas/smoke testing is needed for this preview.

## Expected limitations and troubleshooting

- Zone type names/IDs and metadata vary between drivers. Unknown types use a generic
  binary sensor; missing `is_open` stays Unknown, never silently Closed.
- The GET_SETUP fallback can provide only metadata on some drivers. Such sensors
  need a zone event to establish state. Metadata refresh preserves the last push
  state while connected; a failed connection clears that assumption.
- A failed read makes discovered zones unavailable; a later successful refresh
  recovers them. A valid empty list marks previously discovered zones unavailable.
- Discovery occurs on integration setup. After adding zones in Control4 or if initial
  discovery failed, reload the Control4 integration to retry discovery.
- Existing standalone sensors can coexist with the new panel-zone sensors. They
  have separate unique IDs; no existing registry entities are removed or renamed.
- Look for `Discovered N zones for security partition ...` in Home Assistant logs.
  `Could not discover zones ...` means the driver response needs investigation.
- When reporting a problem, include the affected zone ID, observed state versus
  expected state, and relevant Control4 integration log lines. Redact credentials,
  tokens, addresses, and names you do not want to share.

## Roll back

Restore `/config/control4-before-alarm-zones` to
`/config/custom_components/control4` and restart Home Assistant. Its original
manifest restores the original library requirement automatically. Keep your existing
Control4 config entry. New zone entities may remain in the registry as unavailable;
remove those only after deciding not to continue testing. Existing item entities
keep their original identities.

## Developer tests

Use Python 3.14 in an isolated environment:

```sh
pip install -r requirements-test.txt
python - <<'PY'
import json, subprocess, sys
with open('custom_components/control4/manifest.json') as f:
    requirements = json.load(f)['requirements']
subprocess.check_call([sys.executable, '-m', 'pip', 'install', *requirements])
PY
python -m pytest -q
```

## Night mode reports

Some DSC drivers accept `Instant Stay` but report their armed mode as `Night`.
The integration recognizes that report as Armed Night after checking explicit
user-configured mappings. This does not change any configured arm command.
