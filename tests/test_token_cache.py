"""Credential cache validation, isolation and lifecycle."""

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from custom_components.control4.token_cache import DirectorTokenCache


@pytest.fixture
def cache():
    entry = SimpleNamespace(
        entry_id="entry",
        data={
            "host": "controller",
            "username": "user",
            "controller_unique_id": "id",
        },
    )
    with patch("custom_components.control4.token_cache.Store") as store, patch(
        "custom_components.control4.token_cache.time.time", return_value=1000
    ):
        store.return_value.async_load = AsyncMock()
        store.return_value.async_save = AsyncMock()
        store.return_value.async_remove = AsyncMock()
        result = DirectorTokenCache(object(), entry)
        store.assert_called_once_with(
            ANY, 1, "control4.entry.director_token", private=True
        )
        yield result


@pytest.mark.asyncio
async def test_round_trip_preserves_absolute_expiry_and_metadata(cache):
    await cache.async_save("credential", 2000, "3.4")
    saved = cache.store.async_save.call_args.args[0]
    cache.store.async_load.return_value = saved
    assert await cache.async_load() == saved
    assert cache.data["expires_at"] == 2000
    assert cache.data["sw_version"] == "3.4"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires", [None, "2000", True, 999, 1000, float("nan"), float("inf")]
)
async def test_invalid_or_expired_cache_is_ignored(cache, expires):
    cache.store.async_load.return_value = {
        "identity": cache.identity,
        "token": "credential",
        "expires_at": expires,
    }
    assert await cache.async_load() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["host", "username", "controller_unique_id"])
async def test_cache_cannot_cross_account_or_controller(cache, key):
    identity = {**cache.identity, key: "other"}
    cache.store.async_load.return_value = {
        "identity": identity,
        "token": "credential",
        "expires_at": 2000,
    }
    assert await cache.async_load() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [None, [], "corrupt", {}, {"token": "credential"}])
async def test_missing_or_malformed_cache(cache, data):
    cache.store.async_load.return_value = data
    assert await cache.async_load() is None


@pytest.mark.asyncio
async def test_unreadable_cache_is_optional(cache):
    cache.store.async_load.side_effect = OSError("secret")
    assert await cache.async_load() is None


@pytest.mark.asyncio
async def test_remove_deletes_credential(cache):
    await cache.async_remove()
    cache.store.async_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_storage_survives_new_instance_and_is_private(tmp_path):
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(
        entry_id="entry",
        data={
            "host": "controller",
            "username": "user",
            "controller_unique_id": "id",
        },
    )
    cache = DirectorTokenCache(hass, entry)
    with patch("custom_components.control4.token_cache.time.time", return_value=1000):
        await cache.async_save("credential", 2000, "3.4")
        restored = DirectorTokenCache(hass, entry)
        assert (await restored.async_load())["token"] == "credential"
        path = tmp_path / ".storage" / "control4.entry.director_token"
        assert path.stat().st_mode & 0o077 == 0
        await restored.async_remove()
        assert not path.exists()
    await hass.async_stop()
