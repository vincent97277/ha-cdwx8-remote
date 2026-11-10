"""Set up a CDWX8 remote by listening for a button press."""

import asyncio
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_last_service_info,
    async_register_advertisement_callback,
    async_register_callback,
)
from homeassistant.components.bluetooth.models import BluetoothCallbackReplay
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .advertisement import press_frames
from .const import CONF_UUID_PREFIX, DOMAIN

MAC_ADDRESS = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}")
SCAN_TIMEOUT = 30


def _detect_remote(info: BluetoothServiceInfoBleak) -> tuple[str, str] | None:
    """Validate the observed CDWX8 signature and read both setup values."""
    address = info.address.upper()
    if not MAC_ADDRESS.fullmatch(address):
        return None
    signature = b"\x01\x01" + bytes.fromhex(address[6:].replace(":", ""))
    for frame in press_frames(info.raw):
        prefix = frame[:6]
        if prefix == signature:
            return address, prefix.hex()
    return None


class JiuhaoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one remote with a distinct Bluetooth address."""

    VERSION = 1
    _discovered_address: str | None = None
    _detected: tuple[str, str] | None = None
    _scan_task: asyncio.Task[tuple[str, str] | None] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer press detection first and keep manual setup available."""
        return self.async_show_menu(step_id="user", menu_options=["scan", "manual"])

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Use a discovered address and check whether the packet is a press."""
        address = discovery_info.address.upper()
        if not MAC_ADDRESS.fullmatch(address):
            return self.async_abort(reason="unsupported_address")
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        self._discovered_address = address
        self.context["title_placeholders"] = {"name": f"Jiuhao CDWX8 {address}"}
        self._detected = _detect_remote(discovery_info)
        if self._detected:
            return await self.async_step_confirm()
        return await self.async_step_bluetooth_ready()

    async def async_step_bluetooth_ready(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open a scan scoped to the discovered remote."""
        assert self._discovered_address is not None
        if user_input is not None:
            latest = async_last_service_info(self.hass, self._discovered_address, False)
            if latest and (detected := _detect_remote(latest)):
                self._detected = detected
                return await self.async_step_confirm()
            return await self.async_step_scan()
        return self.async_show_form(
            step_id="bluetooth_ready",
            description_placeholders={"address": self._discovered_address},
        )

    async def async_step_scan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Prompt the user to press a key while HA listens."""
        if self._scan_task is None:
            self._scan_task = self.hass.async_create_task(
                self._async_wait_for_press(), eager_start=False
            )
        if not self._scan_task.done():
            return self.async_show_progress(
                step_id="scan", progress_action="press_key", progress_task=self._scan_task
            )
        self._detected = self._scan_task.result()
        self._scan_task = None
        return self.async_show_progress_done(
            next_step_id="confirm" if self._detected else "scan_timeout"
        )

    async def _async_wait_for_press(self) -> tuple[str, str] | None:
        """Take one valid packet and release the scanner on completion or cancel."""
        found = self.hass.loop.create_future()

        @callback
        def receive(info: BluetoothServiceInfoBleak) -> None:
            if found.done() or not (detected := _detect_remote(info)):
                return
            if self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, detected[0]):
                return
            found.set_result(detected)

        if self._discovered_address:
            unsubscribe = async_register_advertisement_callback(
                self.hass, receive, self._discovered_address
            )
        else:

            @callback
            def receive_change(info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
                receive(info)

            unsubscribe = async_register_callback(
                self.hass,
                receive_change,
                {"connectable": False},
                BluetoothScanningMode.PASSIVE,
                replay=BluetoothCallbackReplay.DISABLED,
            )
        try:
            async with asyncio.timeout(SCAN_TIMEOUT):
                return await found
        except TimeoutError:
            return None
        finally:
            unsubscribe()

    async def async_step_scan_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user retry detection or enter known values."""
        return self.async_show_menu(step_id="scan_timeout", menu_options=["scan", "manual"])

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the detected remote before saving it."""
        assert self._detected is not None
        address, prefix = self._detected
        # The same packet may also open a built-in Bluetooth discovery flow.
        await self.async_set_unique_id(address, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self._create_remote(address, prefix)
        return self.async_show_form(
            step_id="confirm", description_placeholders={"address": address}
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep measured settings usable as a fallback."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = self._discovered_address or user_input[CONF_ADDRESS].strip().upper()
            if not MAC_ADDRESS.fullmatch(address):
                errors[CONF_ADDRESS] = "invalid_address"
            try:
                prefix = bytes.fromhex(user_input[CONF_UUID_PREFIX])
            except ValueError:
                prefix = b""
            if len(prefix) != 6:
                errors[CONF_UUID_PREFIX] = "invalid_prefix"
            if not errors:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self._create_remote(address, prefix.hex())

        fields = {vol.Required(CONF_UUID_PREFIX): str}
        if self._discovered_address is None:
            fields = {vol.Required(CONF_ADDRESS): str, **fields}
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), user_input),
            errors=errors,
        )

    def _create_remote(self, address: str, prefix: str) -> ConfigFlowResult:
        """Store the same entry shape used by previously installed remotes."""
        return self.async_create_entry(
            title=f"Jiuhao CDWX8 {address}",
            data={CONF_ADDRESS: address, CONF_UUID_PREFIX: prefix},
        )
