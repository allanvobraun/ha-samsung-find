from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api.client import SamsungFindApiClient
from .api.dto import SessionData
from .const import DATA_ENTRIES, DATA_SERVICE_REGISTERED, DOMAIN, PLATFORMS, SERVICE_RING_DEVICE
from .exceptions import SamsungFindAuthError
from .helpers import async_start_reauth_flow, get_entry_config
from .models import SamsungFindRuntimeData
from .coordinator import SamsungFindDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Samsung Find integration domain."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_ENTRIES, {})

    if not hass.data[DOMAIN].get(DATA_SERVICE_REGISTERED):
        hass.services.async_register(DOMAIN, SERVICE_RING_DEVICE, _build_ring_handler(hass))
        hass.data[DOMAIN][DATA_SERVICE_REGISTERED] = True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Samsung Find from a config entry."""

    config = get_entry_config(entry)
    client = SamsungFindApiClient(hass)
    client.set_session(SessionData(jsessionid=config.jsessionid))

    coordinator = SamsungFindDataUpdateCoordinator(
        hass=hass,
        entry=entry,
        client=client,
        selected_device_id=config.selected_device_id,
    )
    await coordinator.async_config_entry_first_refresh()

    runtime_data = SamsungFindRuntimeData(client=client, coordinator=coordinator, config=config)
    hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id] = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Samsung Find config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN][DATA_ENTRIES].pop(entry.entry_id, None)
    return unload_ok


def _build_ring_handler(hass: HomeAssistant):
    async def _async_handle_ring_service(call: ServiceCall) -> None:
        runtimes = _get_runtime_entries(hass)
        target_device_ids = _extract_target_device_ids(hass, call)

        if not target_device_ids:
            if len(runtimes) != 1:
                raise HomeAssistantError(
                    "A Samsung Find target is required when multiple config entries are loaded"
                )
            runtime = next(iter(runtimes.values()))
            await _async_ring_runtime(hass, runtime)
            return

        matching_runtimes = [
            runtime
            for runtime in runtimes.values()
            if _runtime_matches_target_device(hass, runtime, target_device_ids)
        ]
        if not matching_runtimes:
            raise HomeAssistantError("No Samsung Find config entry matches the requested target")

        for runtime in matching_runtimes:
            await _async_ring_runtime(hass, runtime)

    return _async_handle_ring_service


def _get_runtime_entries(hass: HomeAssistant) -> dict[str, SamsungFindRuntimeData]:
    return hass.data[DOMAIN][DATA_ENTRIES]


def _extract_target_device_ids(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    device_ids = set(_normalize_list(call.data.get(ATTR_DEVICE_ID)))
    entity_ids = _normalize_list(call.data.get(ATTR_ENTITY_ID))
    if not entity_ids:
        return device_ids

    entity_registry = er.async_get(hass)
    for entity_id in entity_ids:
        entry = entity_registry.async_get(entity_id)
        if entry and entry.device_id:
            device_ids.add(entry.device_id)
    return device_ids


def _normalize_list(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [item for item in value if item]


async def _async_ring_runtime(hass: HomeAssistant, runtime: SamsungFindRuntimeData) -> None:
    try:
        await runtime.client.async_ring_device(runtime.coordinator.data.device)
    except SamsungFindAuthError:
        entry = hass.config_entries.async_get_entry(runtime.coordinator.config_entry.entry_id)
        if entry is not None:
            await async_start_reauth_flow(hass, entry)
        raise HomeAssistantError("Samsung Find session expired and reauthentication was started")


def _runtime_matches_target_device(
    hass: HomeAssistant,
    runtime: SamsungFindRuntimeData,
    target_device_ids: set[str],
) -> bool:
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, runtime.config.selected_device_id)})
    return device_entry is not None and device_entry.id in target_device_ids
