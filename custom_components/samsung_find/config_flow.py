from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .api.client import SamsungFindApiClient
from .api.dto import LoginStageOneResult, SamsungFindDevice, SessionData, StoredConfigEntryData
from .const import CONF_SELECTED_DEVICE_ID, CONF_SELECTED_DEVICE_NAME, DOMAIN
from .exceptions import (
    SamsungFindAuthError,
    SamsungFindError,
    SamsungFindLoginTimeout,
    SamsungFindValidationError,
)
from .helpers import generate_qr_code_base64, get_entry_config


class SamsungFindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Samsung Find config and reauth flows."""

    VERSION = 1
    MINOR_VERSION = 1

    reauth_entry: ConfigEntry | None = None

    _client: SamsungFindApiClient | None = None
    _stage_one_task: asyncio.Task[None] | None = None
    _stage_two_task: asyncio.Task[None] | None = None
    _stage_one_result: LoginStageOneResult | None = None
    _session_data: SessionData | None = None
    _available_devices: list[SamsungFindDevice] = []
    _flow_error: str | None = None

    async def _async_stage_one(self) -> None:
        try:
            if self._client is None:
                self._client = SamsungFindApiClient(self.hass)
            self._stage_one_result = await self._client.async_start_qr_login()
        except SamsungFindValidationError:
            self._flow_error = "validation"
        except SamsungFindError:
            self._flow_error = "auth"

    async def _async_stage_two(self) -> None:
        try:
            assert self._client is not None
            self._session_data = await self._client.async_finish_qr_login()
            self._client.set_session(self._session_data)
            self._available_devices = await self._client.async_list_devices()
        except SamsungFindLoginTimeout:
            self._flow_error = "login_timeout"
        except SamsungFindValidationError:
            self._flow_error = "validation"
        except SamsungFindAuthError:
            self._flow_error = "reauth_required"
        except SamsungFindError:
            self._flow_error = "auth"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._stage_one_task is None:
            self._stage_one_task = self.hass.async_create_task(self._async_stage_one())

        if not self._stage_one_task.done():
            return self.async_show_progress(
                step_id="user",
                progress_action="task_stage_one",
                progress_task=self._stage_one_task,
            )

        if self._flow_error:
            return self.async_show_progress_done(next_step_id="finish")

        return self.async_show_progress_done(next_step_id="auth_stage_two")

    async def async_step_auth_stage_two(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        assert self._stage_one_result is not None

        if self._stage_two_task is None:
            self._stage_two_task = self.hass.async_create_task(self._async_stage_two())

        if not self._stage_two_task.done():
            qr_url = self._stage_one_result.qr_url
            return self.async_show_progress(
                step_id="auth_stage_two",
                progress_action="task_stage_two",
                progress_task=self._stage_two_task,
                description_placeholders={
                    "qr_code": generate_qr_code_base64(qr_url),
                    "url": qr_url,
                    "code": qr_url.rsplit("/", maxsplit=1)[-1],
                },
            )

        if self._flow_error:
            return self.async_show_progress_done(next_step_id="finish")
        if not self._available_devices:
            self._flow_error = "no_devices"
            return self.async_show_progress_done(next_step_id="finish")

        return self.async_show_progress_done(next_step_id="select_device")

    async def async_step_select_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None and self._session_data is not None:
            selected_device_id = user_input[CONF_SELECTED_DEVICE_ID]
            selected_device = next(
                device for device in self._available_devices if device.device_id == selected_device_id
            )
            data = StoredConfigEntryData(
                jsessionid=self._session_data.jsessionid,
                selected_device_id=selected_device.device_id,
                selected_device_name=selected_device.model_name,
            )
            if self.reauth_entry is not None:
                return self.async_update_reload_and_abort(
                    self.reauth_entry,
                    data=data.model_dump(by_alias=True),
                    reason="reauth_successful",
                )

            await self.async_set_unique_id(f"samsung_find_{selected_device.device_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=selected_device.model_name,
                data=data.model_dump(by_alias=True),
            )

        device_map = {device.device_id: device.model_name for device in self._available_devices}
        default_device = next(iter(device_map))
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_DEVICE_ID, default=default_device): vol.In(device_map),
                }
            ),
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_form(step_id="finish", errors={"base": self._flow_error or "unknown"})

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self.reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))
        return await self.async_step_user()

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        self.reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if self.reauth_entry is None:
            return self.async_show_form(step_id="finish", errors={"base": "unknown"})

        if self._client is None:
            config = get_entry_config(self.reauth_entry)
            self._client = SamsungFindApiClient(self.hass)
            self._client.set_session(SessionData(jsessionid=config.jsessionid))
            self._session_data = SessionData(jsessionid=config.jsessionid)
            try:
                self._available_devices = await self._client.async_list_devices()
            except SamsungFindAuthError:
                self._flow_error = "reauth_required"
                return self.async_show_form(step_id="finish", errors={"base": self._flow_error})
            except SamsungFindValidationError:
                self._flow_error = "validation"
                return self.async_show_form(step_id="finish", errors={"base": self._flow_error})
            except SamsungFindError:
                self._flow_error = "unknown"
                return self.async_show_form(step_id="finish", errors={"base": self._flow_error})

        return await self.async_step_select_device(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SamsungFindOptionsFlow(config_entry)


class SamsungFindOptionsFlow(OptionsFlow):
    """Handle Samsung Find options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._client: SamsungFindApiClient | None = None
        self._available_devices: list[SamsungFindDevice] = []
        self._flow_error: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        config = get_entry_config(self._config_entry)
        if self._client is None:
            self._client = SamsungFindApiClient(self.hass)
            self._client.set_session(SessionData(jsessionid=config.jsessionid))
            try:
                self._available_devices = await self._client.async_list_devices()
            except SamsungFindAuthError:
                self._flow_error = "reauth_required"
            except SamsungFindValidationError:
                self._flow_error = "validation"
            except SamsungFindError:
                self._flow_error = "unknown"

        if user_input is not None:
            selected_device_id = user_input[CONF_SELECTED_DEVICE_ID]
            selected_device = next(
                device for device in self._available_devices if device.device_id == selected_device_id
            )
            self.hass.config_entries.async_schedule_reload(self._config_entry.entry_id)
            return self.async_create_entry(
                title="",
                data={
                    CONF_SELECTED_DEVICE_ID: selected_device.device_id,
                    CONF_SELECTED_DEVICE_NAME: selected_device.model_name,
                },
            )

        if self._flow_error is not None:
            return self.async_show_form(step_id="init", data_schema=vol.Schema({}), errors={"base": self._flow_error})
        if not self._available_devices:
            return self.async_show_form(step_id="init", data_schema=vol.Schema({}), errors={"base": "no_devices"})

        device_map = {device.device_id: device.model_name for device in self._available_devices}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_DEVICE_ID, default=config.selected_device_id): vol.In(device_map),
                }
            ),
        )
