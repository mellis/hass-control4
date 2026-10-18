"""Driver-reported alarm modes need not equal the configured arm command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState

from custom_components.control4.alarm_control_panel import Control4AlarmControlPanel
from custom_components.control4.const import (
    CONF_ALARM_AWAY_MODE,
    CONF_ALARM_CUSTOM_BYPASS_MODE,
    CONF_ALARM_HOME_MODE,
    CONF_ALARM_NIGHT_MODE,
    CONF_ALARM_VACATION_MODE,
    CONF_CONTROLLER_UNIQUE_ID,
)


def alarm(reported, **overrides):
    config = {
        CONF_CONTROLLER_UNIQUE_ID: "controller",
        CONF_ALARM_AWAY_MODE: "Away",
        CONF_ALARM_HOME_MODE: "Stay",
        CONF_ALARM_NIGHT_MODE: "Instant Stay",
        CONF_ALARM_CUSTOM_BYPASS_MODE: "(not set)",
        CONF_ALARM_VACATION_MODE: "(not set)",
    }
    config.update(overrides)
    return Control4AlarmControlPanel(
        config,
        MagicMock(),
        "Partition 1",
        65,
        "Panel",
        "DSC",
        "TL-280",
        63,
        "House",
        {"PARTITION_STATE": "ARMED", "ARMED_TYPE": reported},
        True,
        [],
    )


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ("Night", AlarmControlPanelState.ARMED_NIGHT),
        ("Instant Stay", AlarmControlPanelState.ARMED_NIGHT),
        (" night ", AlarmControlPanelState.ARMED_NIGHT),
        ("Away", AlarmControlPanelState.ARMED_AWAY),
        ("Stay", AlarmControlPanelState.ARMED_HOME),
        ("Other driver mode", None),
        (None, None),
        ("(not set)", None),
    ],
)
def test_reported_arm_mode(reported, expected):
    assert alarm(reported).alarm_state == expected


def test_explicit_mapping_takes_precedence_over_night_alias():
    assert (
        alarm("Night", **{CONF_ALARM_HOME_MODE: "Night"}).alarm_state
        == AlarmControlPanelState.ARMED_HOME
    )


@pytest.mark.asyncio
async def test_night_alias_does_not_change_the_command_sent():
    entity = alarm("Night")
    api = MagicMock()
    api.set_arm = AsyncMock()
    with patch.object(entity, "create_api_object", return_value=api):
        await entity.async_alarm_arm_night("1234")
    api.set_arm.assert_awaited_once_with("1234", "Instant Stay")
