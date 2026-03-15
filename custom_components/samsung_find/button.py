from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import _async_ring_runtime
from .const import DATA_ENTRIES, DOMAIN
from .helpers import build_device_info
from .models import SamsungFindRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Samsung Find button entities."""

    runtime = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    async_add_entities([SamsungFindRingButton(runtime)])


class SamsungFindRingButton(CoordinatorEntity, ButtonEntity):
    """Button that asks Samsung Find to ring the selected device."""

    _attr_has_entity_name = True
    _attr_name = "Ring"
    _attr_icon = "mdi:phone-ring-outline"

    def __init__(self, runtime: SamsungFindRuntimeData) -> None:
        super().__init__(runtime.coordinator)
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.config.selected_device_id}_ring"

    @property
    def device_info(self):
        return build_device_info(self.coordinator.data.device)

    @property
    def entity_picture(self) -> str | None:
        device = self.coordinator.data.device
        if device.icons is None:
            return None
        return device.icons.colored_icon

    async def async_press(self) -> None:
        await _async_ring_runtime(self.hass, self._runtime)
