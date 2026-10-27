"""BLE session and polling for a Neil climatizador."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import timedelta
import logging

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    ACCEPTED_MARKER,
    CHAR_UUID,
    COMMAND_DELAY_SECONDS,
    CONF_ACCESS_KEY,
    DEFAULT_TITLE,
    DOMAIN,
    FRAME_LENGTH,
    KEY_MARKER,
    PAIR_DELAY_SECONDS,
    PAIR_MARKER,
    READ_POWER,
    READ_TIMER,
    SPEED_MAX,
    UPDATE_INTERVAL_SECONDS,
    parse_power,
    parse_timer,
    power_frame,
    timer_frame,
)

_LOGGER = logging.getLogger(__name__)

CONNECTION_ERRORS = (
    BleakError,
    TimeoutError,
    EOFError,
    BrokenPipeError,
    OSError,
)


class PairingAbortedError(Exception):
    """The peripheral did not offer an acceptable access key."""


@dataclass(frozen=True, slots=True)
class NeilState:
    """Last parsed power and timer state."""

    fan_on: bool = False
    speed: int = 0
    pump_on: bool = False
    bulb_on: bool = False
    water_level: int = 0
    timer_on: bool = False
    timer_selected_hours: int = 0
    timer_remaining_hours: int = 0
    last_speed: int = 0


class NeilCoordinator(DataUpdateCoordinator[NeilState]):
    """Hold one GATT connection and serialize every read and write."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Set up the coordinator for a config entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DEFAULT_TITLE,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
            always_update=False,
        )
        self.address: str = entry.data[CONF_ADDRESS]
        raw_key = entry.data.get(CONF_ACCESS_KEY, [])
        self._key = bytes(raw_key) if isinstance(raw_key, list) else b""
        self._title = entry.title
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._state = NeilState()
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            connections={(CONNECTION_BLUETOOTH, self.address)},
            manufacturer="Neil",
            model="Climatizador",
            name=entry.title,
        )

    async def _async_update_data(self) -> NeilState:
        """Read power, then timer."""
        async with self._lock:
            try:
                power = await self._exchange(READ_POWER)
                timer = await self._exchange(READ_TIMER)
            except CONNECTION_ERRORS as err:
                await self._drop_client()
                raise UpdateFailed(f"Neil climatizador unavailable: {err}") from err
            if len(power) < FRAME_LENGTH:
                raise UpdateFailed(f"Short power frame ({len(power)} bytes)")
            self._apply_power(power)
            if len(timer) >= FRAME_LENGTH:
                self._apply_timer(timer)
            else:
                _LOGGER.debug("Short timer frame %s", timer.hex())
            return self._state

    async def async_set_power(
        self,
        fan_on: bool | None = None,
        speed: int | None = None,
        pump_on: bool | None = None,
        bulb_on: bool | None = None,
    ) -> None:
        """Write a full power frame, filling gaps from the last known state."""
        async with self._lock:
            state = self._state
            frame = power_frame(
                state.fan_on if fan_on is None else fan_on,
                state.speed if speed is None else speed,
                state.pump_on if pump_on is None else pump_on,
                state.bulb_on if bulb_on is None else bulb_on,
            )
            data = await self._command(frame)
            if len(data) >= FRAME_LENGTH:
                self._apply_power(data)
                self.async_set_updated_data(self._state)
            if len(data) < FRAME_LENGTH or data[0] != 0:
                _LOGGER.warning("Power command not acknowledged: %s", data.hex())
                raise HomeAssistantError(
                    "Neil climatizador did not acknowledge the power command"
                )

    async def async_set_timer(self, on: bool, hours: int) -> None:
        """Write the timer. Zero hours is sent as timer off."""
        if hours <= 0:
            on = False
            hours = 0
        async with self._lock:
            data = await self._command(timer_frame(on, hours))
            if len(data) >= FRAME_LENGTH:
                self._apply_timer(data)
                self.async_set_updated_data(self._state)
            if len(data) < FRAME_LENGTH or data[0] != 0:
                _LOGGER.warning("Timer command not acknowledged: %s", data.hex())
                raise HomeAssistantError(
                    "Neil climatizador did not acknowledge the timer command"
                )

    async def async_shutdown(self) -> None:
        """Stop polling and drop the GATT connection."""
        await super().async_shutdown()
        async with self._lock:
            await self._drop_client()

    async def _command(self, frame: bytes) -> bytes:
        """Exchange one command frame. Caller holds the lock."""
        try:
            return await self._exchange(frame)
        except CONNECTION_ERRORS as err:
            await self._drop_client()
            self.async_set_update_error(UpdateFailed(str(err)))
            raise HomeAssistantError("Neil climatizador is unavailable") from err

    async def _exchange(self, frame: bytes) -> bytes:
        """Write with response, wait, read. Caller holds the lock."""
        await self._ensure_connected()
        client = self._client
        if client is None or not client.is_connected:
            raise BleakError("peripheral unavailable")
        _LOGGER.debug("TX %s", frame.hex())
        await client.write_gatt_char(CHAR_UUID, frame, response=True)
        await asyncio.sleep(COMMAND_DELAY_SECONDS)
        data = bytes(await client.read_gatt_char(CHAR_UUID))
        _LOGGER.debug("RX %s", data.hex())
        return data

    async def _ensure_connected(self) -> None:
        """Connect and present a saved key that starts with 0x51."""
        if self._client is not None and self._client.is_connected:
            return
        await self._drop_client()
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise BleakError("peripheral unavailable")

        def resolve_device() -> BLEDevice:
            return (
                bluetooth.async_ble_device_from_address(
                    self.hass, self.address, connectable=True
                )
                or device
            )

        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self._title,
            self._on_disconnect,
            ble_device_callback=resolve_device,
        )
        self._client = client
        try:
            await self._present_key(client)
        except Exception:
            await self._drop_client()
            raise

    async def _present_key(self, client: BleakClient) -> None:
        """Write the saved key when it is a Q payload. Do not log the key."""
        if not self._key or self._key[0] != KEY_MARKER:
            return
        _LOGGER.debug("Presenting access key len %d", len(self._key))
        await client.write_gatt_char(CHAR_UUID, self._key, response=True)
        await asyncio.sleep(PAIR_DELAY_SECONDS)
        response = bytes(await client.read_gatt_char(CHAR_UUID))
        marker = response[0] if response else None
        _LOGGER.debug(
            "Access key response marker %s len %d",
            hex(marker) if marker is not None else "none",
            len(response),
        )

    async def _drop_client(self) -> None:
        """Disconnect without logging the key."""
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        except BleakError:
            _LOGGER.debug("Disconnect failed for %s", self.address)

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Bleak disconnected us. The next poll reconnects."""
        _LOGGER.debug("Disconnected from %s", self.address)

    def _apply_power(self, frame: bytes) -> None:
        """Store power bytes. Remember the last non-zero speed for turn-on."""
        parsed = parse_power(frame)
        if parsed is None:
            return
        fan_on, speed, pump_on, bulb_on, water = parsed
        raw_speed = frame[2]
        if raw_speed > SPEED_MAX:
            _LOGGER.debug("Speed byte %s outside 0-10", raw_speed)
        if 1 <= raw_speed <= SPEED_MAX:
            last_speed = raw_speed
        else:
            last_speed = self._state.last_speed
        self._state = replace(
            self._state,
            fan_on=fan_on,
            speed=speed,
            pump_on=pump_on,
            bulb_on=bulb_on,
            water_level=water,
            last_speed=last_speed,
        )

    def _apply_timer(self, frame: bytes) -> None:
        """Store timer bytes 1-3."""
        parsed = parse_timer(frame)
        if parsed is None:
            return
        timer_on, selected, remaining = parsed
        self._state = replace(
            self._state,
            timer_on=timer_on,
            timer_selected_hours=selected,
            timer_remaining_hours=remaining,
        )


type NeilConfigEntry = ConfigEntry[NeilCoordinator]


class NeilEntity(CoordinatorEntity[NeilCoordinator]):
    """Base entity for one climatizador."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Bind the entity to the coordinator device."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    @property
    def data(self) -> NeilState:
        """Return the last coordinator snapshot."""
        return self.coordinator.data


async def async_pair(hass: HomeAssistant, device: BLEDevice) -> bytes:
    """Connect, resolve the access key, and disconnect.

    The returned bytes are the key to persist. The buffer itself is never logged.
    """
    address = device.address

    def resolve_device() -> BLEDevice:
        return (
            bluetooth.async_ble_device_from_address(hass, address, connectable=True)
            or device
        )

    client = await establish_connection(
        BleakClientWithServiceCache,
        device,
        device.name or DEFAULT_TITLE,
        ble_device_callback=resolve_device,
    )
    try:
        payload = bytes(await client.read_gatt_char(CHAR_UUID))
        return await _access_key_from_payload(client, payload)
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except BleakError:
            _LOGGER.debug("Disconnect after pairing failed for %s", address)


async def _access_key_from_payload(client: BleakClient, payload: bytes) -> bytes:
    """Apply the P/Q/R handshake. Anything else aborts."""
    if not payload:
        raise PairingAbortedError
    marker = payload[0]
    _LOGGER.debug("Pairing marker %s len %d", hex(marker), len(payload))
    if marker == PAIR_MARKER:
        key = bytearray(payload)
        key[0] = KEY_MARKER
        stored = bytes(key)
        await client.write_gatt_char(CHAR_UUID, stored, response=True)
        await asyncio.sleep(PAIR_DELAY_SECONDS)
        response = bytes(await client.read_gatt_char(CHAR_UUID))
        response_marker = response[0] if response else None
        _LOGGER.debug(
            "Pairing response marker %s len %d",
            hex(response_marker) if response_marker is not None else "none",
            len(response),
        )
        if response_marker != ACCEPTED_MARKER:
            raise PairingAbortedError
        return stored
    if marker in (KEY_MARKER, ACCEPTED_MARKER):
        return bytes(payload)
    if all(byte == 0 for byte in payload[1:]):
        raise PairingAbortedError
    _LOGGER.debug("Refusing pairing payload with marker %s", hex(marker))
    raise PairingAbortedError
