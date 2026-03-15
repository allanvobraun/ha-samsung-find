from __future__ import annotations

from base64 import b64encode
from html import unescape
from io import BytesIO

import qrcode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .api.dto import SamsungFindDevice, StoredConfigEntryData
from .const import DOMAIN, MANUFACTURER


def build_device_info(device: SamsungFindDevice) -> DeviceInfo:
    """Build the Home Assistant device metadata for a Samsung Find device."""

    return DeviceInfo(
        identifiers={(DOMAIN, device.device_id)},
        manufacturer=MANUFACTURER,
        name=unescape(unescape(device.model_name)),
        model=device.model_id,
        configuration_url="https://smartthingsfind.samsung.com/",
    )


def generate_qr_code_base64(data: str) -> str:
    """Encode a QR code image as base64 for config flow rendering."""

    qr_code = qrcode.QRCode()
    qr_code.add_data(data)
    image = qr_code.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return b64encode(buffer.getvalue()).decode("utf-8")


def get_entry_config(entry: ConfigEntry) -> StoredConfigEntryData:
    """Return the merged config/option payload validated as a DTO."""

    return StoredConfigEntryData.model_validate({**entry.data, **entry.options})


async def async_start_reauth_flow(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Trigger Home Assistant's standard reauth flow for an entry."""

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
