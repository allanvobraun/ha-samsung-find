from __future__ import annotations

from custom_components.samsung_find.api.dto import (
    DeviceListResponse,
    DeviceOperation,
    SessionData,
    StoredConfigEntryData,
    extract_battery_level,
)


def test_device_list_response_unescapes_model_names() -> None:
    response = DeviceListResponse.model_validate(
        {
            "deviceList": [
                {
                    "dvceID": "device-1",
                    "usrId": "user-1",
                    "modelName": "Allan&amp;#39;s Galaxy S24",
                    "modelID": "SM-S921B",
                }
            ]
        }
    )

    assert response.device_list[0].model_name == "Allan's Galaxy S24"


def test_extract_battery_level_supports_named_and_numeric_values() -> None:
    named_level = extract_battery_level([DeviceOperation(oprnType="CHECK_CONNECTION", battery="LOW")])
    numeric_level = extract_battery_level([DeviceOperation(oprnType="CHECK_CONNECTION", battery="87")])

    assert named_level == 15
    assert numeric_level == 87


def test_stored_config_entry_data_accepts_aliases() -> None:
    data = StoredConfigEntryData.model_validate(
        {
            "jsessionid": "session-id",
            "selected_device_id": "device-1",
            "selected_device_name": "Galaxy S24",
        }
    )

    assert data == StoredConfigEntryData(
        jsessionid=SessionData(jsessionid="session-id").jsessionid,
        selected_device_id="device-1",
        selected_device_name="Galaxy S24",
    )
