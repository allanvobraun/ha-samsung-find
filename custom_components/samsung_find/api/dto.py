from __future__ import annotations

from html import unescape
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..const import BATTERY_LEVELS, CONF_JSESSIONID, CONF_SELECTED_DEVICE_ID, CONF_SELECTED_DEVICE_NAME


class SamsungFindModel(BaseModel):
    """Base DTO model for Samsung Find payloads."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", str_strip_whitespace=True)


class LoginStageOneResult(SamsungFindModel):
    """Result of the first QR-login stage."""

    qr_url: str
    state: str


class SessionData(SamsungFindModel):
    """Persisted Samsung session data."""

    jsessionid: str = Field(alias=CONF_JSESSIONID)


class StoredConfigEntryData(SamsungFindModel):
    """Config entry data persisted by Home Assistant."""

    jsessionid: str = Field(alias=CONF_JSESSIONID)
    selected_device_id: str = Field(alias=CONF_SELECTED_DEVICE_ID)
    selected_device_name: str = Field(alias=CONF_SELECTED_DEVICE_NAME)


class SamsungFindIcons(SamsungFindModel):
    """Optional Samsung device icons."""

    colored_icon: str | None = Field(default=None, alias="coloredIcon")


class SamsungFindDevice(SamsungFindModel):
    """Samsung Find device metadata."""

    device_id: str = Field(alias="dvceID")
    user_id: str = Field(alias="usrId")
    model_name: str = Field(alias="modelName")
    model_id: str | None = Field(default=None, alias="modelID")
    device_type_code: str | None = Field(default=None, alias="deviceTypeCode")
    sub_type: str | None = Field(default=None, alias="subType")
    icons: SamsungFindIcons | None = None

    @field_validator("model_name", mode="before")
    @classmethod
    def unescape_model_name(cls, value: str) -> str:
        """Samsung returns HTML-escaped device names."""

        return unescape(unescape(value))


class DeviceListResponse(SamsungFindModel):
    """Samsung Find device list response."""

    device_list: list[SamsungFindDevice] = Field(alias="deviceList")


class CsrfTokenData(SamsungFindModel):
    """Nested CSRF token payload returned by Samsung login."""

    token: str


class SignInXhrResponse(SamsungFindModel):
    """Samsung QR-login XHR response."""

    csrf: CsrfTokenData = Field(alias="_csrf")


class QrPollResponse(SamsungFindModel):
    """Samsung QR polling response."""

    result_code: str = Field(alias="rtnCd")
    next_url: str | None = Field(default=None, alias="nextURL")


class DeviceDetailRequest(SamsungFindModel):
    """Payload used to request Samsung device details."""

    device_id: str = Field(alias="dvceId")
    remove_device: list[str] = Field(default_factory=list, alias="removeDevice")


class DeviceOperation(SamsungFindModel):
    """Operation data returned for a Samsung device."""

    operation_type: str = Field(alias="oprnType")
    battery: str | int | None = None
    extra: dict[str, Any] | None = None


class DeviceDetailResponse(SamsungFindModel):
    """Details returned for a selected Samsung device."""

    operation: list[DeviceOperation] = Field(default_factory=list)


class RingDeviceRequest(SamsungFindModel):
    """Payload used to request ringing a Samsung device."""

    device_id: str = Field(alias="dvceId")
    operation: str
    user_id: str = Field(alias="usrId")
    status: str = "start"
    lock_message: str = Field(alias="lockMessage")


class RingResponse(SamsungFindModel):
    """Best-effort normalization of the Samsung ring response."""

    ok: bool = True
    status_code: int
    result_code: str | None = Field(default=None, alias="rtnCd")
    message: str | None = Field(default=None, alias="rtnMsg")
    body: str | None = None


class SelectedDeviceSnapshot(SamsungFindModel):
    """Coordinator data for the selected Samsung device."""

    device: SamsungFindDevice
    battery_level: int | None = None
    operations: list[DeviceOperation] = Field(default_factory=list)


def extract_battery_level(operations: list[DeviceOperation]) -> int | None:
    """Extract a numeric battery level from Samsung operation data."""

    for operation in operations:
        if operation.operation_type != "CHECK_CONNECTION" or operation.battery is None:
            continue

        if isinstance(operation.battery, int):
            return operation.battery

        return BATTERY_LEVELS.get(operation.battery, _coerce_battery(operation.battery))
    return None


def _coerce_battery(raw_value: str) -> int | None:
    try:
        return int(raw_value)
    except ValueError:
        return None
