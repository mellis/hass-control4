"""Follow the driver's arm PIN policy without removing the disarm keypad."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.alarm_control_panel.const import CodeFormat
from homeassistant.exceptions import ServiceValidationError

from custom_components.control4 import alarm_control_panel as platform
from custom_components.control4.const import (
    CONF_ALARM_ARM_STATES,
    CONF_ALARM_AWAY_MODE,
    CONF_CONTROLLER_UNIQUE_ID,
    CONF_DIRECTOR,
    CONTROL4_ENTITY_TYPE,
    DOMAIN,
)


async def setup_alarm(setup):
    director = MagicMock()
    director.get_item_setup = AsyncMock(return_value=setup)
    entry = MagicMock(entry_id="test")
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "test": {
                CONF_DIRECTOR: director,
                CONF_CONTROLLER_UNIQUE_ID: "controller",
                CONF_ALARM_ARM_STATES: set(),
                CONF_ALARM_AWAY_MODE: "Away",
            }
        }
    }
    add_entities = MagicMock()
    item = {
        "type": CONTROL4_ENTITY_TYPE,
        "id": 65,
        "name": "Partition 1",
        "roomName": "House",
        "parentId": 63,
    }
    with (
        patch.object(platform.entity_platform, "current_platform") as current,
        patch.object(platform, "get_items_of_category", AsyncMock(return_value=[item])),
        patch.object(
            platform, "director_get_entry_variables", AsyncMock(return_value={})
        ),
        patch.object(platform, "C4SecurityPanel") as api,
    ):
        current.get.return_value = None
        api.return_value.get_emergency_types = AsyncMock(return_value=[])
        await platform.async_setup_entry(hass, entry, add_entities)
    return add_entities.call_args.args[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,expected",
    [
        (False, False),
        (True, True),
        (None, True),
        ("false", True),
        (0, True),
    ],
)
async def test_setup_arm_requirement(value, expected):
    entity = await setup_alarm(
        {"setup": {"enabled": True, "code_required_to_arm": value}}
    )
    assert entity.code_arm_required is expected
    assert entity.code_format == CodeFormat.NUMBER


@pytest.mark.asyncio
@pytest.mark.parametrize("setup", [{}, {"setup": {}}, {"setup": None}])
async def test_missing_setup_requires_arm_code(setup):
    entity = await setup_alarm(setup)
    assert entity.code_arm_required is True


@pytest.mark.asyncio
async def test_partition_push_updates_requirement_and_retains_it_when_omitted():
    entity = await setup_alarm({"setup": {"code_required_to_arm": True}})
    with patch.object(entity, "async_write_ha_state"):
        for data, expected in [
            ({"code_required_to_arm": False}, False),
            ({"state": "DISARMED_READY"}, False),
            ({"code_required_to_arm": True}, True),
        ]:
            await entity._update_callback(
                65, {"evtName": "OnDataToUI", "data": {"partition_state": data}}
            )
            assert entity.code_arm_required is expected


@pytest.mark.asyncio
async def test_code_free_arm_and_disarm_code_forwarding():
    entity = await setup_alarm({"setup": {"code_required_to_arm": False}})
    api = MagicMock(set_arm=AsyncMock(), set_disarm=AsyncMock())
    with patch.object(entity, "create_api_object", return_value=api):
        await entity.async_handle_alarm_arm_away()
        api.set_arm.assert_awaited_once_with("", "Away")
        await entity.async_handle_alarm_disarm("1234")
        api.set_disarm.assert_awaited_once_with("1234")


@pytest.mark.asyncio
async def test_required_code_still_blocks_code_free_arm():
    entity = await setup_alarm({"setup": {"code_required_to_arm": True}})
    with patch.object(entity, "create_api_object") as api:
        with pytest.raises(ServiceValidationError):
            await entity.async_handle_alarm_arm_away()
        api.assert_not_called()
