from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_find.api.dto import SelectedDeviceSnapshot
from custom_components.samsung_find.const import (
    CONF_JSESSIONID,
    CONF_SELECTED_DEVICE_ID,
    CONF_SELECTED_DEVICE_NAME,
    DOMAIN,
    SERVICE_RING_DEVICE,
)


def _snapshot(*, battery_level: int | None = 87) -> SelectedDeviceSnapshot:
    return SelectedDeviceSnapshot.model_validate(
        {
            "device": {
                "dvceID": "device-1",
                "usrId": "user-1",
                "modelName": "Galaxy S24",
                "modelID": "SM-S921B",
            },
            "battery_level": battery_level,
            "operations": [],
        }
    )


async def test_setup_entry_creates_entities_and_service_can_ring(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_JSESSIONID: "session-id",
            CONF_SELECTED_DEVICE_ID: "device-1",
            CONF_SELECTED_DEVICE_NAME: "Galaxy S24",
        },
        title="Galaxy S24",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.samsung_find.coordinator.SamsungFindApiClient.async_get_selected_device_snapshot",
            AsyncMock(return_value=_snapshot()),
        ),
        patch(
            "custom_components.samsung_find.api.client.SamsungFindApiClient.async_ring_device",
            AsyncMock(),
        ) as ring_mock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get("button.galaxy_s24_ring") is not None
        assert hass.states.get("sensor.galaxy_s24_battery") is not None

        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "device-1")})
        assert device_entry is not None

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RING_DEVICE,
            {ATTR_DEVICE_ID: [device_entry.id]},
            blocking=True,
        )

        ring_mock.assert_awaited_once()


async def test_setup_entry_skips_battery_sensor_when_unavailable(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_JSESSIONID: "session-id",
            CONF_SELECTED_DEVICE_ID: "device-1",
            CONF_SELECTED_DEVICE_NAME: "Galaxy S24",
        },
        title="Galaxy S24",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.samsung_find.coordinator.SamsungFindApiClient.async_get_selected_device_snapshot",
        AsyncMock(return_value=_snapshot(battery_level=None)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get("button.galaxy_s24_ring") is not None
        assert hass.states.get("sensor.galaxy_s24_battery") is None
