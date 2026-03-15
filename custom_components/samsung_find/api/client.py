from __future__ import annotations

import asyncio
import logging
import random
import re
import string
from time import monotonic
from typing import Any

from aiohttp import ClientResponse, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pydantic import ValidationError
from yarl import URL

from ..const import DEFAULT_LOCK_MESSAGE, LOGIN_POLL_INTERVAL_SECONDS, LOGIN_TIMEOUT_SECONDS
from ..exceptions import (
    SamsungFindApiError,
    SamsungFindAuthError,
    SamsungFindLoginTimeout,
    SamsungFindValidationError,
)
from .dto import (
    DeviceDetailRequest,
    DeviceDetailResponse,
    DeviceListResponse,
    LoginStageOneResult,
    QrPollResponse,
    RingDeviceRequest,
    RingResponse,
    SamsungFindDevice,
    SelectedDeviceSnapshot,
    SessionData,
    SignInXhrResponse,
    extract_battery_level,
)

_LOGGER = logging.getLogger(__name__)

URL_BASE = "https://smartthingsfind.samsung.com"
URL_PRE_SIGNIN = (
    "https://account.samsung.com/accounts/v1/FMM2/signInGate?"
    "state={state}&redirect_uri=https:%2F%2Fsmartthingsfind.samsung.com%2Flogin.do"
    "&response_type=code&client_id=ntly6zvfpn&scope=iot.client&locale=en_US"
    "&acr_values=urn:samsungaccount:acr:basic&goBackURL=https:%2F%2Fsmartthingsfind.samsung.com%2Flogin"
)
URL_QR_CODE_SIGNIN = "https://account.samsung.com/accounts/v1/FMM2/signInWithQrCode"
URL_SIGNIN_XHR = "https://account.samsung.com/accounts/v1/FMM2/signInXhr"
URL_QR_POLL = "https://account.samsung.com/accounts/v1/FMM2/signInWithQrCodeProc"
URL_SIGNIN_SUCCESS = "https://account.samsung.com{next_url}"
URL_GET_CSRF = f"{URL_BASE}/chkLogin.do"
URL_DEVICE_LIST = f"{URL_BASE}/device/getDeviceList.do"
URL_SET_LAST_DEVICE = f"{URL_BASE}/device/setLastSelect.do"
URL_ADD_OPERATION = f"{URL_BASE}/dm/addOperation.do"

QR_URL_PATTERN = re.compile(r"https://signin\.samsung\.com/key/[^'\"]+")
REDIRECT_PATTERN = re.compile(r"window\.location\.href\s*=\s*[\"']([^\"']+)[\"']")


class SamsungFindApiClient:
    """Thin client for the reverse-engineered Samsung Find web API."""

    def __init__(self, hass: HomeAssistant, session: ClientSession | None = None) -> None:
        self._hass = hass
        self._session = session or async_get_clientsession(hass)
        self._csrf: str | None = None

    @property
    def session(self) -> ClientSession:
        return self._session

    @property
    def csrf(self) -> str | None:
        return self._csrf

    def set_session(self, session_data: SessionData) -> None:
        """Seed the aiohttp cookie jar with the saved JSESSIONID."""

        self._session.cookie_jar.update_cookies(
            {"JSESSIONID": session_data.jsessionid},
            response_url=URL(URL_BASE),
        )

    async def async_start_qr_login(self) -> LoginStageOneResult:
        """Prepare Samsung's QR-based sign-in and return the QR URL."""

        self._session.cookie_jar.clear()
        self._csrf = None
        state = "".join(random.choices(string.ascii_letters + string.digits, k=16))

        await self._read_text(self._session.get(URL_PRE_SIGNIN.format(state=state)), error_hint="pre-signin")
        html = await self._read_text(self._session.get(URL_QR_CODE_SIGNIN), error_hint="qr-page")

        match = QR_URL_PATTERN.search(html)
        if match is None:
            raise SamsungFindValidationError("Samsung QR code URL was not found in the login page")

        return LoginStageOneResult(qr_url=match.group(0), state=state)

    async def async_finish_qr_login(
        self,
        *,
        timeout_seconds: int = LOGIN_TIMEOUT_SECONDS,
        poll_interval_seconds: int = LOGIN_POLL_INTERVAL_SECONDS,
    ) -> SessionData:
        """Wait for the QR login to complete and return the SmartThings Find session."""

        payload = await self._read_json(self._session.get(URL_SIGNIN_XHR), error_hint="signin-xhr")
        try:
            xhr_response = SignInXhrResponse.model_validate(payload)
        except ValidationError as err:
            raise SamsungFindValidationError("Samsung sign-in XHR payload is invalid") from err

        deadline = monotonic() + timeout_seconds
        next_url: str | None = None

        while monotonic() < deadline:
            await asyncio.sleep(poll_interval_seconds)
            poll_payload = await self._read_json(
                self._session.post(URL_QR_POLL, json={}, headers={"X-Csrf-Token": xhr_response.csrf.token}),
                error_hint="qr-poll",
            )
            try:
                poll_response = QrPollResponse.model_validate(poll_payload)
            except ValidationError as err:
                raise SamsungFindValidationError("Samsung QR poll payload is invalid") from err

            if poll_response.result_code == "SUCCESS":
                next_url = poll_response.next_url
                break

        if next_url is None:
            raise SamsungFindLoginTimeout("Samsung QR login timed out")

        html = await self._read_text(
            self._session.get(URL_SIGNIN_SUCCESS.format(next_url=next_url)),
            error_hint="signin-success",
        )
        match = REDIRECT_PATTERN.search(html)
        if match is None:
            raise SamsungFindValidationError("Samsung redirect URL was not found after login")

        await self._read_text(self._session.get(match.group(1)), error_hint="stf-redirect")

        cookie = self._session.cookie_jar.filter_cookies(URL(URL_BASE)).get("JSESSIONID")
        if cookie is None:
            raise SamsungFindValidationError("Samsung Find JSESSIONID cookie is missing after login")

        return SessionData(jsessionid=cookie.value)

    async def async_fetch_csrf(self) -> str:
        """Retrieve a fresh CSRF token for the current JSESSIONID."""

        async with self._session.get(URL_GET_CSRF) as response:
            body = await response.text()
            if response.status != 200 or body == "Logout":
                raise SamsungFindAuthError(
                    "Samsung Find session is not valid",
                    status=response.status,
                    body=body,
                )

            csrf = response.headers.get("_csrf")
            if not csrf:
                raise SamsungFindValidationError("Samsung Find CSRF header was missing")

            self._csrf = csrf
            return csrf

    async def async_list_devices(self) -> list[SamsungFindDevice]:
        """Return the devices visible in Samsung Find."""

        csrf = await self._ensure_csrf()
        payload = await self._read_json(
            self._session.post(
                f"{URL_DEVICE_LIST}?_csrf={csrf}",
                headers={"Accept": "application/json"},
                data={},
            ),
            error_hint="device-list",
        )
        try:
            return DeviceListResponse.model_validate(payload).device_list
        except ValidationError as err:
            raise SamsungFindValidationError("Samsung device list payload is invalid") from err

    async def async_fetch_device_detail(self, device_id: str) -> DeviceDetailResponse:
        """Fetch operation data for a Samsung Find device."""

        csrf = await self._ensure_csrf()
        request = DeviceDetailRequest(device_id=device_id)
        payload = await self._read_json(
            self._session.post(
                f"{URL_SET_LAST_DEVICE}?_csrf={csrf}",
                headers={"Accept": "application/json"},
                json=request.model_dump(by_alias=True),
            ),
            error_hint="device-detail",
        )
        try:
            return DeviceDetailResponse.model_validate(payload)
        except ValidationError as err:
            raise SamsungFindValidationError("Samsung device detail payload is invalid") from err

    async def async_get_selected_device_snapshot(self, device_id: str) -> SelectedDeviceSnapshot:
        """Build the coordinator snapshot for the selected Samsung device."""

        devices = await self.async_list_devices()
        selected_device = next((device for device in devices if device.device_id == device_id), None)
        if selected_device is None:
            raise SamsungFindApiError(f"Selected device {device_id} is no longer available")

        detail = await self.async_fetch_device_detail(device_id)
        return SelectedDeviceSnapshot(
            device=selected_device,
            battery_level=extract_battery_level(detail.operation),
            operations=detail.operation,
        )

    async def async_ring_device(
        self,
        device: SamsungFindDevice,
        *,
        lock_message: str = DEFAULT_LOCK_MESSAGE,
    ) -> RingResponse:
        """Trigger Samsung Find to ring a device."""

        csrf = await self._ensure_csrf()
        request = RingDeviceRequest(
            device_id=device.device_id,
            operation="RING",
            user_id=device.user_id,
            lock_message=lock_message,
        )

        try:
            return await self._async_post_ring(request, csrf)
        except SamsungFindApiError as err:
            if isinstance(err, SamsungFindAuthError):
                raise
            _LOGGER.debug("Samsung ring request failed once, refreshing CSRF and retrying")
            csrf = await self.async_fetch_csrf()
            return await self._async_post_ring(request, csrf)

    async def _async_post_ring(self, request: RingDeviceRequest, csrf: str) -> RingResponse:
        payload, body, status = await self._read_json_or_text(
            self._session.post(
                f"{URL_ADD_OPERATION}?_csrf={csrf}",
                json=request.model_dump(by_alias=True),
            ),
            error_hint="ring-device",
        )
        if payload is None:
            return RingResponse(ok=status == 200, status_code=status, body=body)

        try:
            return RingResponse(status_code=status, body=body, **payload)
        except ValidationError as err:
            raise SamsungFindValidationError("Samsung ring response payload is invalid") from err

    async def _ensure_csrf(self) -> str:
        if self._csrf is None:
            return await self.async_fetch_csrf()
        return self._csrf

    async def _read_text(self, request_context: Any, *, error_hint: str) -> str:
        async with request_context as response:
            text = await response.text()
            self._raise_for_response(response, text, error_hint=error_hint)
            return text

    async def _read_json(self, request_context: Any, *, error_hint: str) -> dict[str, Any]:
        async with request_context as response:
            text = await response.text()
            self._raise_for_response(response, text, error_hint=error_hint)
            try:
                return await response.json(content_type=None)
            except Exception as err:
                raise SamsungFindValidationError(
                    f"Samsung {error_hint} response was not valid JSON"
                ) from err

    async def _read_json_or_text(
        self,
        request_context: Any,
        *,
        error_hint: str,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        async with request_context as response:
            text = await response.text()
            self._raise_for_response(response, text, error_hint=error_hint)
            try:
                payload = await response.json(content_type=None)
            except Exception:
                return None, text, response.status
            return payload, text, response.status

    def _raise_for_response(self, response: ClientResponse, body: str, *, error_hint: str) -> None:
        if response.status == 401 or body == "Logout":
            raise SamsungFindAuthError(
                f"Samsung authentication failed during {error_hint}",
                status=response.status,
                body=body,
            )
        if response.status >= 400:
            raise SamsungFindApiError(
                f"Samsung API error during {error_hint}",
                status=response.status,
                body=body,
            )
