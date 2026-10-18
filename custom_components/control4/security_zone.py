"""Discover and track zones exposed by a security partition, rather than items."""

from __future__ import annotations

import logging
from datetime import timedelta

from aiohttp import ClientError
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from pyControl4.alarm import C4SecurityPanel
from pyControl4.error_handling import C4Exception, Unauthorized

from .const import CONF_CONTROLLER_UNIQUE_ID, CONF_DIRECTOR, CONF_WEBSOCKET, DOMAIN

_LOGGER = logging.getLogger(__name__)
ZONE_CLASSES = {
    1: BinarySensorDeviceClass.OPENING,
    2: BinarySensorDeviceClass.DOOR,
    3: BinarySensorDeviceClass.WINDOW,
    4: BinarySensorDeviceClass.DOOR,
    5: BinarySensorDeviceClass.MOTION,
    6: BinarySensorDeviceClass.SMOKE,
    7: BinarySensorDeviceClass.GAS,
    8: BinarySensorDeviceClass.CO,
    9: BinarySensorDeviceClass.HEAT,
    10: BinarySensorDeviceClass.MOISTURE,
    11: BinarySensorDeviceClass.SMOKE,
    14: BinarySensorDeviceClass.OPENING,
    15: BinarySensorDeviceClass.GARAGE_DOOR,
    16: BinarySensorDeviceClass.COLD,
}


def zone_id(value):
    """Canonicalize numeric IDs without truncating floats or accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return str(int(value))
    except ValueError:
        return None


def zone_bool(value):
    """Decode booleans without treating the string 'false' as true."""
    if isinstance(value, bool):
        return value
    if value in (0, "0", "false", "False"):
        return False
    if value in (1, "1", "true", "True"):
        return True
    return None


class SecurityZoneCoordinator(DataUpdateCoordinator):
    """One read per partition every 30 seconds, with immediate push updates."""

    def __init__(self, hass, entry, entry_data, panel):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Control4 zones {panel['id']}",
            update_interval=timedelta(seconds=30),
        )
        self.entry_data = entry_data
        self.panel = panel

    async def _async_update_data(self):
        try:
            api = C4SecurityPanel(self.entry_data[CONF_DIRECTOR], self.panel["id"])
            try:
                zones = await api.get_zones()
            except Unauthorized:
                raise
            except C4Exception:
                zones = None
            if zones is None:
                # Older drivers expose zone metadata/state through GET_SETUP.
                setup = await self.entry_data[CONF_DIRECTOR].get_item_setup(
                    self.panel["id"]
                )
                zones = (
                    setup.get("panel_setup", {}).get("all_zones", {}).get("zone_info")
                )
                if isinstance(zones, dict):
                    zones = [zones]
            if not isinstance(zones, list):
                raise UpdateFailed("No supported zone list returned by this partition")
            snapshot = {}
            for zone in zones:
                if (
                    not isinstance(zone, dict)
                    or (key := zone_id(zone.get("id"))) is None
                ):
                    raise UpdateFailed("Invalid zone record returned by partition")
                # GET_SETUP may supply metadata only. Preserve the latest push
                # state while healthy, but never carry it across a failed read.
                previous = (
                    (self.data or {}).get(key, {}) if self.last_update_success else {}
                )
                snapshot[key] = {**previous, **zone}
            return snapshot
        except (
            ClientError,
            C4Exception,
            TimeoutError,
            ValueError,
            TypeError,
            AttributeError,
        ) as err:
            raise UpdateFailed(
                f"Unable to read security zones ({type(err).__name__})"
            ) from err


class Control4SecurityZone(CoordinatorEntity, BinarySensorEntity):
    """A passive binary sensor identified by controller, partition and zone ID."""

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.zone_key = key
        self.panel_id = int(coordinator.panel["id"])
        self._attr_unique_id = (
            f"{coordinator.entry_data[CONF_CONTROLLER_UNIQUE_ID]}_"
            f"partition_{self.panel_id}_zone_{key}"
        )
        zone = coordinator.data[key]
        self._attr_name = str(
            zone.get("name") or f"{coordinator.panel['name']} Zone {key}"
        )
        type_id = zone_id(zone.get("type_id"))
        self._attr_device_class = ZONE_CLASSES.get(int(type_id)) if type_id else None
        controller = coordinator.entry_data[CONF_CONTROLLER_UNIQUE_ID]
        parent = coordinator.panel.get("parentId")
        if parent is not None:
            # Match Control4Entity's parent-device identifier, so zones join
            # the same alarm hardware as the existing partition alarm entity.
            # Omit metadata to preserve the device's vendor details and name.
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, str(parent))},
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{controller}_partition_{self.panel_id}")},
                name=coordinator.panel.get("name") or f"Partition {self.panel_id}",
                via_device=(DOMAIN, controller),
            )

    @property
    def available(self):
        return super().available and self.zone_key in (self.coordinator.data or {})

    @property
    def is_on(self):
        return zone_bool(
            (self.coordinator.data or {}).get(self.zone_key, {}).get("is_open")
        )

    @property
    def extra_state_attributes(self):
        zone = (self.coordinator.data or {}).get(self.zone_key, {})
        attrs = {"alarm_partition_id": self.panel_id, "alarm_zone_id": self.zone_key}
        for field in ("type_id", "is_bypassed", "can_bypass", "room_name"):
            if field in zone:
                attrs[field] = zone[field]
        return attrs

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Migrate the short-lived partition-device preview after entities have
        # attached to their existing hardware. Never remove a device with entities
        # or a device belonging to another config entry.
        if self.coordinator.panel.get("parentId") is not None and self.registry_entry:
            devices = dr.async_get(self.hass)
            controller = self.coordinator.entry_data[CONF_CONTROLLER_UNIQUE_ID]
            previous = devices.async_get_device(
                identifiers={(DOMAIN, f"{controller}_partition_{self.panel_id}")}
            )
            if (
                previous is not None
                and previous.config_entry_id == self.registry_entry.config_entry_id
                and not er.async_entries_for_device(
                    er.async_get(self.hass), previous.id
                )
            ):
                devices.async_remove_device(previous.id)
        self.coordinator.entry_data[CONF_WEBSOCKET].add_item_callback(
            self.panel_id, self._zone_event
        )
        self.async_on_remove(
            lambda: self.coordinator.entry_data[CONF_WEBSOCKET].remove_item_callback(
                self.panel_id, self._zone_event
            )
        )

    async def _zone_event(self, device, message):
        if message is False:
            self.coordinator.async_set_update_error(
                UpdateFailed("Control4 websocket disconnected")
            )
            return
        if not isinstance(message, dict) or message.get("evtName") != "OnDataToUI":
            return
        if message.get("refresh"):
            await self.coordinator.async_request_refresh()
            return
        data = message.get("data", {})
        zone = data.get("zone_state") if isinstance(data, dict) else None
        if not isinstance(zone, dict) or zone_id(zone.get("id")) != self.zone_key:
            return
        # Do not mutate the event shared with the panel and other zone callbacks.
        # A partial event cannot restore a failed/stale whole-partition snapshot.
        if not self.coordinator.last_update_success:
            await self.coordinator.async_request_refresh()
            return
        snapshot = dict(self.coordinator.data or {})
        snapshot[self.zone_key] = {**snapshot.get(self.zone_key, {}), **zone}
        self.coordinator.async_set_updated_data(snapshot)
