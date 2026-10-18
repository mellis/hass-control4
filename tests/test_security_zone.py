"""Panel-only zones tested against Home Assistant's actual entity/coordinator APIs."""

from copy import deepcopy
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.control4 import C4WebsocketConnectionTracker
from custom_components.control4.binary_sensor import async_setup_entry
from custom_components.control4.const import (
    CONF_CONTROLLER_UNIQUE_ID,
    CONF_DIRECTOR,
    CONF_DIRECTOR_ALL_ITEMS,
    CONF_WEBSOCKET,
    DOMAIN,
)
from custom_components.control4.security_zone import (
    Control4SecurityZone,
    SecurityZoneCoordinator,
    zone_bool,
)


@pytest_asyncio.fixture
async def env(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Control4",
        source="user",
        data={},
        options={},
        unique_id="controller",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    director = MagicMock()
    director.send_post_request = AsyncMock(
        return_value='{"zones":{"zone":[{"id":1,"name":"Front Door","type_id":2,"is_open":false},{"id":2,"name":"Window","type_id":3,"is_open":true}]}}'
    )
    director.get_item_setup = AsyncMock(return_value={})
    websocket = MagicMock()
    data = {
        CONF_DIRECTOR: director,
        CONF_WEBSOCKET: websocket,
        CONF_CONTROLLER_UNIQUE_ID: "controller",
        CONF_DIRECTOR_ALL_ITEMS: [],
    }
    hass.data[DOMAIN] = {entry.entry_id: data}
    coordinator = SecurityZoneCoordinator(
        hass, entry, data, {"id": 500, "name": "Partition 1"}
    )
    yield hass, entry, data, coordinator
    await hass.async_stop(force=True)


@pytest.mark.asyncio
async def test_discovery_when_no_standalone_sensors_exist(env):
    hass, entry, _data, _ = env
    add = MagicMock()
    with patch(
        "custom_components.control4.binary_sensor.get_items_of_category",
        new=AsyncMock(
            side_effect=[[], [{"id": 500, "name": "Partition 1", "type": 7}]]
        ),
    ):
        await async_setup_entry(hass, entry, add)
    entities = add.call_args.args[0]
    assert len(entities) == 2
    assert entities[0].unique_id == "controller_partition_500_zone_1"
    assert entities[0].is_on is False
    assert entities[1].is_on is True
    assert entities[0].device_class == "door"


@pytest.mark.asyncio
async def test_zone_events_are_filtered_and_do_not_mutate_shared_payload(env):
    _, _, _, c = env
    await c.async_refresh()
    one, two = Control4SecurityZone(c, "1"), Control4SecurityZone(c, "2")
    message = {
        "evtName": "OnDataToUI",
        "data": {"zone_state": {"id": "1", "is_open": True}},
    }
    original = deepcopy(message)
    await two._zone_event(500, message)
    assert one.is_on is False
    await one._zone_event(500, message)
    assert one.is_on is True
    assert two.is_on is True
    assert message == original
    assert one.extra_state_attributes["alarm_zone_id"] == "1"


@pytest.mark.asyncio
async def test_polling_corrects_missed_event_and_unavailable_on_failure(env):
    _, _, data, c = env
    await c.async_refresh()
    zone = Control4SecurityZone(c, "1")
    assert zone.available
    await zone._zone_event(
        500,
        {"evtName": "OnDataToUI", "data": {"zone_state": {"id": 1, "is_open": True}}},
    )
    assert zone.is_on is True
    await c.async_refresh()
    assert zone.is_on is False
    data[CONF_DIRECTOR].send_post_request.side_effect = TimeoutError
    await c.async_refresh()
    assert not zone.available
    data[CONF_DIRECTOR].send_post_request.side_effect = None
    await c.async_refresh()
    assert zone.available


@pytest.mark.asyncio
async def test_setup_fallback_unknown_state_and_stable_id(env):
    _, _, data, c = env
    data[CONF_DIRECTOR].send_post_request.return_value = "{}"
    data[CONF_DIRECTOR].get_item_setup.return_value = {
        "panel_setup": {
            "all_zones": {"zone_info": {"id": "1", "name": "Renamed", "type_id": 999}}
        }
    }
    await c.async_refresh()
    zone = Control4SecurityZone(c, "1")
    assert zone.is_on is None
    assert zone.device_class is None
    assert zone.unique_id == "controller_partition_500_zone_1"
    assert zone.available


@pytest.mark.asyncio
async def test_same_zone_number_in_another_partition_has_different_identity(env):
    hass, entry, data, c = env
    await c.async_refresh()
    c2 = SecurityZoneCoordinator(hass, entry, data, {"id": 501, "name": "Partition 2"})
    await c2.async_refresh()
    assert (
        Control4SecurityZone(c, "1").unique_id
        != Control4SecurityZone(c2, "1").unique_id
    )


@pytest.mark.asyncio
async def test_disconnect_reconnect_and_selective_unsubscribe(env):
    hass, _, data, c = env
    await c.async_refresh()
    zone = Control4SecurityZone(c, "1")
    zone.hass = hass
    zone.entity_id = "binary_sensor.front_door"
    with patch.object(zone, "async_write_ha_state"):
        await zone.async_added_to_hass()
        data[CONF_WEBSOCKET].add_item_callback.assert_called_once_with(
            500, zone._zone_event
        )
        await zone._zone_event(500, False)
        assert not zone.available
        await zone._zone_event(
            500, {"evtName": "OnDataToUI", "refresh": True, "data": {}}
        )
        assert zone.available
        await zone.async_remove(force_remove=True)
        data[CONF_WEBSOCKET].remove_item_callback.assert_called_once_with(
            500, zone._zone_event
        )


@pytest.mark.asyncio
async def test_connection_tracker_dispatches_callback_lists(env):
    hass, entry, data, _ = env
    callbacks = [AsyncMock(), AsyncMock()]
    data[CONF_WEBSOCKET].item_callbacks = {500: callbacks}
    tracker = C4WebsocketConnectionTracker(hass, entry)
    await tracker.disconnect_callback()
    for cb in callbacks:
        cb.assert_awaited_once_with(500, False)
        cb.reset_mock()
    with patch(
        "custom_components.control4.director_get_entry_variables",
        new=AsyncMock(return_value={}),
    ):
        await tracker.connect_callback()
    for cb in callbacks:
        assert cb.await_args.args[1]["refresh"] is True


@pytest.mark.asyncio
async def test_missing_zone_is_unavailable_and_bad_reply_is_not_empty(env):
    _, _, data, c = env
    await c.async_refresh()
    zone = Control4SecurityZone(c, "1")
    data[CONF_DIRECTOR].send_post_request.return_value = '{"zones":{"zone":[]}}'
    await c.async_refresh()
    assert not zone.available
    data[CONF_DIRECTOR].send_post_request.return_value = "{}"
    await c.async_refresh()
    assert not c.last_update_success


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (False, False),
        (True, True),
        ("false", False),
        ("0", False),
        ("1", True),
        ("true", True),
        (None, None),
        ("unknown", None),
    ],
)
def test_boolean_wire_formats(value, expected):
    assert zone_bool(value) is expected


@pytest.mark.asyncio
async def test_metadata_only_poll_preserves_push_state_until_connection_failure(env):
    _, _, data, c = env
    data[CONF_DIRECTOR].send_post_request.return_value = "{}"
    data[CONF_DIRECTOR].get_item_setup.return_value = {
        "panel_setup": {"all_zones": {"zone_info": [{"id": 1, "name": "Door"}]}}
    }
    await c.async_refresh()
    zone = Control4SecurityZone(c, "1")
    assert zone.is_on is None
    await zone._zone_event(
        500,
        {"evtName": "OnDataToUI", "data": {"zone_state": {"id": 1, "is_open": True}}},
    )
    await c.async_refresh()
    assert zone.is_on is True
    c.async_set_update_error(UpdateFailed("Disconnected"))
    await c.async_refresh()
    assert zone.is_on is None


@pytest.mark.asyncio
async def test_parent_panel_and_disabled_partitions_do_not_create_duplicates(env):
    hass, entry, data, _ = env
    panels = [
        {
            "id": 64,
            "name": "Panel",
            "type": 7,
            "proxy": "securitypanel",
            "parentId": 63,
        },
        {
            "id": 65,
            "name": "Partition 1",
            "type": 7,
            "proxy": "security",
            "parentId": 63,
        },
        {
            "id": 66,
            "name": "Partition 2",
            "type": 7,
            "proxy": "security",
            "parentId": 63,
        },
    ]
    data[CONF_DIRECTOR].get_item_setup.side_effect = lambda item_id: {
        "setup": {"enabled": item_id == 65}
    }
    add = MagicMock()
    with patch(
        "custom_components.control4.binary_sensor.get_items_of_category",
        new=AsyncMock(side_effect=[[], panels]),
    ):
        await async_setup_entry(hass, entry, add)
    assert len(add.call_args.args[0]) == 2
    assert all(entity.panel_id == 65 for entity in add.call_args.args[0])
    data[CONF_DIRECTOR].send_post_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_panel_only_driver_keeps_metadata_fallback(env):
    hass, entry, data, _ = env
    panels = [
        {"id": 64, "name": "Panel", "type": 7, "proxy": "securitypanel", "parentId": 63}
    ]
    add = MagicMock()
    with patch(
        "custom_components.control4.binary_sensor.get_items_of_category",
        new=AsyncMock(side_effect=[[], panels]),
    ):
        await async_setup_entry(hass, entry, add)
    assert len(add.call_args.args[0]) == 2
