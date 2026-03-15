from __future__ import annotations

from dataclasses import dataclass

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api.client import SamsungFindApiClient
from .api.dto import SelectedDeviceSnapshot, StoredConfigEntryData


@dataclass(slots=True)
class SamsungFindRuntimeData:
    """Runtime state stored per config entry."""

    client: SamsungFindApiClient
    coordinator: DataUpdateCoordinator[SelectedDeviceSnapshot]
    config: StoredConfigEntryData
