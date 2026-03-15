from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_ENTRIES, DOMAIN
from .helpers import build_device_info
from .models import SamsungFindRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Samsung Find sensor entities."""

    runtime = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    if runtime.coordinator.data.battery_level is None:
        return

    async_add_entities([SamsungFindBatterySensor(runtime)])


class SamsungFindBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery sensor for the selected Samsung Find device."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime: SamsungFindRuntimeData) -> None:
        super().__init__(runtime.coordinator)
        self._attr_unique_id = f"{runtime.config.selected_device_id}_battery"

    @property
    def device_info(self):
        return build_device_info(self.coordinator.data.device)

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.battery_level
