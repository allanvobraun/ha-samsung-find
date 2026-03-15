from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "samsung_find"
MANUFACTURER = "Samsung"

CONF_JSESSIONID = "jsessionid"
CONF_SELECTED_DEVICE_ID = "selected_device_id"
CONF_SELECTED_DEVICE_NAME = "selected_device_name"

DATA_ENTRIES = "entries"
DATA_SERVICE_REGISTERED = "service_registered"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
DEFAULT_LOCK_MESSAGE = "Home Assistant is ringing your phone!"

LOGIN_TIMEOUT_SECONDS = 120
LOGIN_POLL_INTERVAL_SECONDS = 2

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]

SERVICE_RING_DEVICE = "ring_device"

BATTERY_LEVELS: dict[str, int] = {
    "FULL": 100,
    "MEDIUM": 50,
    "LOW": 15,
    "VERY_LOW": 5,
}
