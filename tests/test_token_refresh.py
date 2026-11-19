"""Token replacement must fail safely and retry without an integration reload."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from pyControl4.error_handling import BadCredentials, Unauthorized

from custom_components.control4 import RefreshTokensObject, refresh_tokens
from custom_components.control4.const import (
    CONF_ACCOUNT,
    CONF_CANCEL_TOKEN_REFRESH_CALLBACK,
    CONF_CONTROLLER_UNIQUE_ID,
    CONF_DIRECTOR,
    CONF_WEBSOCKET,
    DOMAIN,
)


@pytest.fixture
def env():
    entry = MagicMock()
    entry.entry_id = "entry"
    entry.data = {
        "host": "192.168.1.1",
        "username": "user",
        "password": "password",
        CONF_CONTROLLER_UNIQUE_ID: "controller",
    }
    websocket = MagicMock()
    websocket.sio_connect = AsyncMock()
    old_director, old_account = object(), object()
    data = {
        CONF_DIRECTOR: old_director,
        CONF_ACCOUNT: old_account,
        CONF_WEBSOCKET: websocket,
    }
    hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: data}})
    account = MagicMock()
    account.get_account_bearer_token = AsyncMock()
    account.get_director_bearer_token = AsyncMock(
        return_value={"token": "new", "validSeconds": 86400}
    )
    director = MagicMock()
    director.director_bearer_token = "new"
    director.get_all_item_info = AsyncMock(return_value=[])
    with patch("custom_components.control4.C4Account", return_value=account), patch(
        "custom_components.control4.C4Director", return_value=director
    ), patch("custom_components.control4.C4Websocket", type(websocket)), patch(
        "custom_components.control4.aiohttp_client.async_get_clientsession"
    ), patch(
        "custom_components.control4.async_call_later"
    ) as schedule:
        yield SimpleNamespace(**locals())


@pytest.mark.asyncio
async def test_rejected_rest_token_preserves_previous_client(env):
    env.director.get_all_item_info.side_effect = Unauthorized("rejected")
    with pytest.raises(
        ConfigEntryNotReady, match="Director token validation.*Unauthorized"
    ):
        await refresh_tokens(env.hass, env.entry)
    assert env.data[CONF_DIRECTOR] is env.old_director
    assert env.data[CONF_ACCOUNT] is env.old_account
    env.websocket.sio_connect.assert_not_awaited()
    env.schedule.assert_not_called()


@pytest.mark.asyncio
async def test_background_subscription_rejection_rolls_back_and_retries(env, caplog):
    env.websocket.sio_connect.side_effect = Unauthorized("rejected")
    await RefreshTokensObject(env.hass, env.entry).refresh_tokens(None)
    assert env.data[CONF_DIRECTOR] is env.old_director
    assert env.data[CONF_ACCOUNT] is env.old_account
    delay = env.schedule.call_args.kwargs["delay"]
    assert 1 <= delay <= 2
    assert "Authenticated subscription failed (Unauthorized)" in caplog.text
    assert "candidate-token" not in caplog.text


@pytest.mark.asyncio
async def test_retry_recovers_and_only_then_schedules_daily_refresh(env):
    env.websocket.sio_connect.side_effect = [Unauthorized("rejected"), None]
    await RefreshTokensObject(env.hass, env.entry).refresh_tokens(None)
    retry = env.schedule.call_args.kwargs["action"]
    await retry(None)
    assert env.data[CONF_DIRECTOR] is env.director
    assert env.schedule.call_args.kwargs["delay"] == 86100
    assert env.schedule.call_count == 2


@pytest.mark.asyncio
async def test_success_cancels_previous_timer_and_publishes_client(env):
    cancel = MagicMock()
    env.data[CONF_CANCEL_TOKEN_REFRESH_CALLBACK] = cancel
    await refresh_tokens(env.hass, env.entry)
    assert env.data[CONF_DIRECTOR] is env.director
    assert env.data[CONF_ACCOUNT] is env.account
    cancel.assert_called_once()
    assert env.schedule.call_args.kwargs["delay"] == 86100


@pytest.mark.asyncio
@pytest.mark.parametrize("lifetime", [120, 300])
async def test_short_lifetime_refreshes_before_expiry(env, lifetime):
    env.account.get_director_bearer_token.return_value["validSeconds"] = lifetime
    await refresh_tokens(env.hass, env.entry)
    assert env.schedule.call_args.kwargs["delay"] == lifetime / 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lifetime", [None, "invalid", -1, 0, float("nan"), float("inf")]
)
async def test_invalid_lifetime_is_retryable(env, lifetime):
    env.account.get_director_bearer_token.return_value["validSeconds"] = lifetime
    await RefreshTokensObject(env.hass, env.entry).refresh_tokens(None)
    assert env.data[CONF_DIRECTOR] is env.old_director
    assert env.schedule.call_args.kwargs["delay"] <= 2


@pytest.mark.asyncio
async def test_cancelled_subscription_restores_previous_client(env):
    env.websocket.sio_connect.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await refresh_tokens(env.hass, env.entry)
    assert env.data[CONF_DIRECTOR] is env.old_director
    env.schedule.assert_not_called()


@pytest.mark.asyncio
async def test_account_auth_failure_requests_reauth_in_scheduled_refresh(env):
    env.account.get_account_bearer_token.side_effect = BadCredentials(
        "invalid credentials"
    )
    await RefreshTokensObject(env.hass, env.entry).refresh_tokens(None)
    env.entry.async_start_reauth.assert_called_once_with(env.hass)
    env.schedule.assert_not_called()


@pytest.mark.asyncio
async def test_retries_remain_bounded_after_long_outage(env):
    env.account.get_account_bearer_token.side_effect = TimeoutError
    refresher = RefreshTokensObject(env.hass, env.entry)
    refresher.retries = 10000
    await refresher.refresh_tokens(None)
    assert 1 <= env.schedule.call_args.kwargs["delay"] <= 30
