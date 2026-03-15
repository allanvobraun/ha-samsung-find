from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.samsung_find.api.dto import LoginStageOneResult, SamsungFindDevice, SessionData
from custom_components.samsung_find.const import (
    CONF_JSESSIONID,
    CONF_SELECTED_DEVICE_ID,
    CONF_SELECTED_DEVICE_NAME,
    DOMAIN,
)
from custom_components.samsung_find.exceptions import SamsungFindLoginTimeout


async def test_user_flow_creates_entry(hass) -> None:
    with (
        patch(
            "custom_components.samsung_find.config_flow.SamsungFindApiClient.async_start_qr_login",
            AsyncMock(
                return_value=LoginStageOneResult(
                    qr_url="https://signin.samsung.com/key/abc123",
                    state="state",
                )
            ),
        ),
        patch(
            "custom_components.samsung_find.config_flow.SamsungFindApiClient.async_finish_qr_login",
            AsyncMock(return_value=SessionData(jsessionid="session-id")),
        ),
        patch(
            "custom_components.samsung_find.config_flow.SamsungFindApiClient.async_list_devices",
            AsyncMock(
                return_value=[
                    SamsungFindDevice(
                        dvceID="device-1",
                        usrId="user-1",
                        modelName="Galaxy S24",
                        modelID="SM-S921B",
                    )
                ]
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] is FlowResultType.SHOW_PROGRESS

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.SHOW_PROGRESS_DONE

        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.SHOW_PROGRESS

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["step_id"] == "select_device"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_DEVICE_ID: "device-1"},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "Galaxy S24"
        assert result["data"] == {
            CONF_JSESSIONID: "session-id",
            CONF_SELECTED_DEVICE_ID: "device-1",
            CONF_SELECTED_DEVICE_NAME: "Galaxy S24",
        }


async def test_user_flow_handles_login_timeout(hass) -> None:
    with (
        patch(
            "custom_components.samsung_find.config_flow.SamsungFindApiClient.async_start_qr_login",
            AsyncMock(
                return_value=LoginStageOneResult(
                    qr_url="https://signin.samsung.com/key/abc123",
                    state="state",
                )
            ),
        ),
        patch(
            "custom_components.samsung_find.config_flow.SamsungFindApiClient.async_finish_qr_login",
            AsyncMock(side_effect=SamsungFindLoginTimeout("timed out")),
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "auth"}
