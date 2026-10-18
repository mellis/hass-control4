"""Single-setpoint drivers must not use the unused heat/cool channels."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate.const import ClimateEntityFeature

from custom_components.control4.climate import Control4Climate
from custom_components.control4.const import CONF_CONTROLLER_UNIQUE_ID, CONF_DIRECTOR


def thermostat(single=True, scale="CELSIUS", fans=""):
    return Control4Climate(
        {
            CONF_CONTROLLER_UNIQUE_ID: "controller",
            CONF_DIRECTOR: MagicMock(send_post_request=AsyncMock()),
        },
        MagicMock(),
        "Bathroom",
        79,
        "Sinope",
        "Sinope",
        "Thermostat",
        78,
        "Bathroom",
        {
            "SCALE": scale,
            "HVAC_MODE": "Heat",
            "HEAT_SETPOINT_C": 0,
            "SINGLE_SETPOINT_C": 17,
            "SINGLE_SETPOINT_F": 63,
            "FAN_MODES_LIST": fans,
        },
        {
            "has_single_setpoint": single,
            "setpoint_single_resolution_c": 0.5,
            "setpoint_single_resolution_f": 1,
            "setpoint_single_min_c": 5,
            "setpoint_single_max_c": 30,
            "setpoint_single_min_f": 41,
            "setpoint_single_max_f": 86,
        },
    )


@pytest.mark.parametrize(
    "scale,target,step,minimum,maximum",
    [
        ("CELSIUS", 17, 0.5, 5, 30),
        ("FAHRENHEIT", 63, 1, 41, 86),
    ],
)
def test_single_setpoint_display(scale, target, step, minimum, maximum):
    entity = thermostat(scale=scale)
    assert entity.target_temperature == target
    assert entity.target_temperature_step == step
    assert (entity.min_temp, entity.max_temp) == (minimum, maximum)
    assert entity.target_temperature_low is None
    assert entity.target_temperature_high is None
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scale,unit,value", [("CELSIUS", "CELSIUS", 17.5), ("FAHRENHEIT", "FAHRENHEIT", 64)]
)
async def test_single_setpoint_command(scale, unit, value):
    entity = thermostat(scale=scale)
    await entity.async_set_temperature(temperature=value)
    entity.entry_data[CONF_DIRECTOR].send_post_request.assert_awaited_once_with(
        "/api/v1/items/79/commands", "SET_SETPOINT_SINGLE", {unit: value}
    )


@pytest.mark.asyncio
async def test_push_single_setpoint_overrides_initial_variable():
    entity = thermostat()
    await entity._data_to_extra_state_attributes({"setpoint_single_c": 18.5})
    assert entity.target_temperature == 18.5


def test_no_fan_controls_for_empty_driver_modes():
    entity = thermostat()
    assert entity.fan_modes == []
    assert not entity.supported_features & ClimateEntityFeature.FAN_MODE


def test_real_fan_modes_preserved():
    entity = thermostat(single=False, fans="On, Auto,Circulate")
    assert entity.fan_modes == ["on", "auto", "diffuse"]
    assert entity.supported_features & ClimateEntityFeature.FAN_MODE
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE


@pytest.mark.asyncio
async def test_conventional_heat_command_unchanged():
    entity = thermostat(single=False)
    api = MagicMock(set_heat_setpoint_c=AsyncMock())
    assert entity.target_temperature == 0
    with patch.object(entity, "create_api_object", return_value=api):
        await entity.async_set_temperature(temperature=19)
    api.set_heat_setpoint_c.assert_awaited_once_with(19)
    entity.entry_data[CONF_DIRECTOR].send_post_request.assert_not_awaited()
