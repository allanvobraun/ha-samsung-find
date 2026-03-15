from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.client import SamsungFindApiClient
from .api.dto import SelectedDeviceSnapshot
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import SamsungFindAuthError, SamsungFindError

_LOGGER = logging.getLogger(__name__)


class SamsungFindDataUpdateCoordinator(DataUpdateCoordinator[SelectedDeviceSnapshot]):
    """Refresh Samsung Find metadata for the selected device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SamsungFindApiClient,
        selected_device_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.config_entry = entry
        self._client = client
        self._selected_device_id = selected_device_id

    async def _async_update_data(self) -> SelectedDeviceSnapshot:
        try:
            return await self._client.async_get_selected_device_snapshot(self._selected_device_id)
        except SamsungFindAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SamsungFindError as err:
            raise UpdateFailed(str(err)) from err
