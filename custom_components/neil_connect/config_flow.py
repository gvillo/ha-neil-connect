"""Config flow for Neil Connect."""

from __future__ import annotations

import logging
from typing import Any, override

import probatio
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import (
    CONF_ACCESS_KEY,
    CONF_TEMPERATURE_SENSOR,
    DEFAULT_TITLE,
    DOMAIN,
    LOCAL_NAME_MARK,
    SERVICE_UUID,
)
from .coordinator import CONNECTION_ERRORS, PairingAbortedError, async_pair

_LOGGER = logging.getLogger(__name__)


def _names(info: BluetoothServiceInfoBleak) -> list[str]:
    names = [info.name or ""]
    local_name = info.advertisement.local_name
    if local_name:
        names.append(local_name)
    return names


def is_neil(info: BluetoothServiceInfoBleak) -> bool:
    """Return True for a MAXICLIMA advertisement or our GATT service."""
    if any(LOCAL_NAME_MARK in name.upper() for name in _names(info)):
        return True
    return SERVICE_UUID in {uuid.lower() for uuid in info.service_uuids}


def device_title(info: BluetoothServiceInfoBleak) -> str:
    """Advertised name, or the default title when the advert has none."""
    for name in _names(info):
        stripped = name.strip()
        if stripped and stripped != info.address:
            return stripped
    return DEFAULT_TITLE


class NeilConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Bluetooth discovery and a manual MAXICLIMA picker."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}
        self._key: list[int] = []

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Start a flow for a device the Bluetooth integration matched."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": device_title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery, then pair."""
        assert self._discovery_info is not None
        info = self._discovery_info
        title = device_title(info)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_pair(info)
            if not errors:
                return self._entry(info, title)
        return self.async_show_form(
            step_id="bluetooth_confirm",
            errors=errors,
            description_placeholders={"name": title},
        )

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a discovered MAXICLIMA device and pair."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = self._discovered.get(user_input[CONF_ADDRESS])
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info.address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                errors = await self._async_pair(info)
                if not errors:
                    return self._entry(info, device_title(info))

        await bluetooth.async_request_active_scan(self.hass)
        configured = self._async_current_ids(include_ignore=False)
        self._discovered = {
            info.address: info
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.address not in configured and is_neil(info)
        }
        if not self._discovered:
            reason = errors.get("base", "no_devices_found")
            return self.async_abort(reason=reason)

        schema = probatio.Schema(
            {
                probatio.Required(CONF_ADDRESS): probatio.In(
                    {
                        info.address: f"{device_title(info)} ({info.address})"
                        for info in self._discovered.values()
                    }
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _async_pair(self, info: BluetoothServiceInfoBleak) -> dict[str, str]:
        """Pair. An empty dict means the key is stored on the flow."""
        try:
            self._key = list(await async_pair(self.hass, info.device))
        except PairingAbortedError:
            return {"base": "pairing_failed"}
        except CONNECTION_ERRORS:
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error pairing %s", info.address)
            return {"base": "cannot_connect"}
        return {}

    def _entry(
        self, info: BluetoothServiceInfoBleak, title: str
    ) -> ConfigFlowResult:
        """Create the config entry from the key captured in _async_pair."""
        return self.async_create_entry(
            title=title,
            data={
                CONF_ADDRESS: info.address,
                CONF_ACCESS_KEY: self._key,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> NeilConnectOptionsFlow:
        """Room sensor. When set, Cool cycles the pump around a target."""
        return NeilConnectOptionsFlow()


class NeilConnectOptionsFlow(OptionsFlow):
    """Pick a Home Assistant sensor to show as the room temperature."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the temperature sensor selector."""
        if user_input is not None:
            options = dict(self.config_entry.options)
            sensor = user_input.get(CONF_TEMPERATURE_SENSOR) or None
            if sensor:
                options[CONF_TEMPERATURE_SENSOR] = sensor
            else:
                options.pop(CONF_TEMPERATURE_SENSOR, None)
            return self.async_create_entry(data=options)

        schema = probatio.Schema(
            {
                probatio.Optional(CONF_TEMPERATURE_SENSOR): EntitySelector(
                    EntitySelectorConfig(
                        domain="sensor",
                        device_class="temperature",
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, dict(self.config_entry.options)
            ),
        )
