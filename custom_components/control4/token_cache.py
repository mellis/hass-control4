"""Private, per-entry cache of locally validated Director credentials."""

import math
import time

from homeassistant.const import CONF_HOST, CONF_TOKEN, CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import CONF_CONTROLLER_UNIQUE_ID, DOMAIN


class DirectorTokenCache:
    """Persist credentials through HA's atomic storage API, never through logs."""

    def __init__(self, hass, entry):
        self.store = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.director_token", private=True
        )
        self.identity = {
            key: entry.data[key]
            for key in (CONF_HOST, CONF_USERNAME, CONF_CONTROLLER_UNIQUE_ID)
        }
        self.data = None

    async def async_load(self):
        """Return an unexpired token for this account/controller, or None."""
        try:
            data = await self.store.async_load()
        except (HomeAssistantError, OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("identity") != self.identity:
            return None
        token, expires_at = data.get(CONF_TOKEN), data.get("expires_at")
        if (
            not isinstance(token, str)
            or not token
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, (int, float))
            or not math.isfinite(expires_at)
            or expires_at <= time.time()
        ):
            return None
        self.data = data
        return data

    async def async_save(self, token, expires_at, sw_version=None):
        """Save only after local REST and subscription authentication succeed."""
        data = {"identity": self.identity, CONF_TOKEN: token, "expires_at": expires_at}
        if sw_version is not None:
            data["sw_version"] = sw_version
        self.data = data
        await self.store.async_save(data)

    async def async_remove(self):
        """Delete credentials when the config entry is removed."""
        self.data = None
        await self.store.async_remove()
