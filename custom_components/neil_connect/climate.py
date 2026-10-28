"""Climate entity for a Neil climatizador.

Modes are the fan and the evaporative pump. The protocol has no setpoint.
With a room sensor configured, Cool stores a target and cycles the pump
around it. Fan speed stays on this entity either way.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, override

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_TEMPERATURE_SENSOR, SPEED_MAX
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity

_LOGGER = logging.getLogger(__name__)

FAN_MODES = [str(speed) for speed in range(1, SPEED_MAX + 1)]

_BASE_FEATURES = (
    ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

_MIN_C = 16.0
_MAX_C = 35.0
_MIN_F = 61.0
_MAX_F = 95.0
_DEFAULT_C = 24.0
_DEFAULT_F = 75.0
_STEP_C = 0.5
_STEP_F = 1.0
# Pump on at target + 1 °C, off at target - 1 °C. Inside the band it holds.
_BAND_C = 1.0
_BAND_F = 2.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the climate entity."""
    async_add_entities([NeilClimate(entry.runtime_data)])


class NeilClimate(NeilEntity, ClimateEntity, RestoreEntity):
    """Off, fan only, or cool. Fan speeds are 1-10.

    A configured room sensor adds a target. Cool then owns the pump.
    """

    _attr_translation_key = "climatizador"
    _attr_name = "Climatizador"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.COOL]
    _attr_fan_modes = FAN_MODES

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id and remember the last running mode."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_climate"
        self._last_running_mode = HVACMode.FAN_ONLY
        self._requested_mode: HVACMode | None = None
        self._target_temperature: float | None = None
        self._saw_fan_on = False
        self._control_lock = asyncio.Lock()
        self._thermostat_job: asyncio.Task[None] | None = None
        self._thermostat_pending = False

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the setpoint and follow the room sensor."""
        await super().async_added_to_hass()
        if self._thermostat_available:
            await self._async_restore_thermostat()
            if self.data.fan_on:
                self._saw_fan_on = True
            elif self.data.pump_on:
                await self.coordinator.async_set_power(
                    fan_on=False, speed=0, pump_on=False
                )
        entity_id = self._temperature_entity_id()
        if entity_id is not None:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [entity_id], self._async_temperature_changed
                )
            )
            self._schedule_thermostat()
        self.async_write_ha_state()

    async def _async_restore_thermostat(self) -> None:
        """Load the last target. Mode is the fan and the pump on the unit."""
        last = await self.async_get_last_state()
        if last is not None:
            raw = last.attributes.get(ATTR_TEMPERATURE)
            if raw is not None:
                try:
                    self._target_temperature = float(raw)
                except (TypeError, ValueError):
                    self._target_temperature = None
        self._requested_mode = self._mode_from_device()
        if self._requested_mode != HVACMode.OFF:
            self._last_running_mode = self._requested_mode
        if self._target_temperature is None:
            self._target_temperature = self._default_target()

    @callback
    def _async_temperature_changed(self, _event: Event) -> None:
        """Room sensor moved. Cool may cycle the pump."""
        self.async_write_ha_state()
        self._schedule_thermostat()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """A remote power-off leaves Cool. Otherwise re-check the pump."""
        self._adopt_external_off()
        super()._handle_coordinator_update()
        if not self._control_lock.locked():
            self._schedule_thermostat()

    @callback
    def _adopt_external_off(self) -> None:
        """Drop Cool or Fan only when the fan bit clears outside a write."""
        if self._control_lock.locked() or not self._thermostat_available:
            return
        if self.data.fan_on:
            self._saw_fan_on = True
            return
        if not self._saw_fan_on:
            return
        self._saw_fan_on = False
        if self._requested_mode not in (None, HVACMode.OFF):
            self._requested_mode = HVACMode.OFF
            if self.data.pump_on:
                self.hass.async_create_task(
                    self._async_stop_stranded_pump(),
                    name="neil_connect thermostat stop",
                )

    def _schedule_thermostat(self) -> None:
        """Run the pump check soon. A busy check remembers to run again."""
        if not self._thermostat_available or self._requested_mode != HVACMode.COOL:
            return
        if self._target_is_minimum():
            return
        job = self._thermostat_job
        if self._control_lock.locked() or (job is not None and not job.done()):
            self._thermostat_pending = True
            return
        self._thermostat_job = self.hass.async_create_task(
            self._async_apply_thermostat(),
            name="neil_connect thermostat",
        )

    def _finish_thermostat(self) -> None:
        """Run a check that arrived while this write was in flight."""
        if not self._thermostat_pending:
            return
        job = self._thermostat_job
        if (
            job is not None
            and not job.done()
            and job is not asyncio.current_task()
        ):
            return
        self._thermostat_pending = False
        self._thermostat_job = None
        self._schedule_thermostat()

    @property
    def _thermostat_available(self) -> bool:
        """True when the options include a room sensor."""
        return self._temperature_entity_id() is not None

    def _temperature_entity_id(self) -> str | None:
        """Return the optional sensor selected in the integration options."""
        entry = self.coordinator.config_entry
        if entry is None:
            return None
        entity_id = entry.options.get(CONF_TEMPERATURE_SENSOR)
        if not entity_id:
            return None
        return str(entity_id)

    def _room_temperature(self) -> float | None:
        """Read the external sensor. Nothing here is written to the device."""
        entity_id = self._temperature_entity_id()
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _room_temperature_unit(self) -> str:
        """Use the sensor unit so Home Assistant can convert it."""
        entity_id = self._temperature_entity_id()
        if entity_id is not None:
            state = self.hass.states.get(entity_id)
            if state is not None:
                unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if unit in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT):
                    return str(unit)
        return UnitOfTemperature.CELSIUS

    def _uses_fahrenheit(self) -> bool:
        """The sensor reports Fahrenheit."""
        return self.temperature_unit == UnitOfTemperature.FAHRENHEIT

    def _default_target(self) -> float:
        """Starting setpoint before the user picks one."""
        if self._uses_fahrenheit():
            return _DEFAULT_F
        return _DEFAULT_C

    def _band(self) -> float:
        """Deadband half-width in the sensor unit."""
        if self._uses_fahrenheit():
            return _BAND_F
        return _BAND_C

    def _target_is_minimum(self) -> bool:
        """The floor target does not cycle the pump. Cooling stays as set."""
        target = self._target_temperature
        if target is None:
            return False
        return target <= self.min_temp

    def _want_pump(self, current: float, target: float) -> bool:
        """Hold the pump inside the band so a noisy sensor does not chatter."""
        band = self._band()
        if self.data.pump_on:
            return current > target - band
        return current >= target + band

    def _clamped_speed(self, speed: int | None) -> int:
        """Speed 1-10, or the last running speed when the caller did not pass one."""
        if speed is not None:
            return max(1, min(SPEED_MAX, speed))
        if 1 <= self.data.speed <= SPEED_MAX:
            return self.data.speed
        return max(1, self.data.last_speed)

    def _mode_from_device(self) -> HVACMode:
        """Map fan and pump flags onto off, fan only, or cool."""
        if not self.data.fan_on:
            return HVACMode.OFF
        if self.data.pump_on:
            return HVACMode.COOL
        return HVACMode.FAN_ONLY

    @property
    @override
    def supported_features(self) -> ClimateEntityFeature:
        """Target temperature exists only with a room sensor."""
        if self._thermostat_available:
            return _BASE_FEATURES | ClimateEntityFeature.TARGET_TEMPERATURE
        return _BASE_FEATURES

    @property
    @override
    def current_temperature(self) -> float | None:
        """Room temperature from the selected entity."""
        return self._room_temperature()

    @property
    @override
    def native_current_temperature(self) -> float | None:
        """Room temperature from the selected entity."""
        return self._room_temperature()

    @property
    @override
    def temperature_unit(self) -> str:
        """Unit reported by the selected sensor."""
        return self._room_temperature_unit()

    @property
    @override
    def native_temperature_unit(self) -> str:
        """Unit reported by the selected sensor."""
        return self._room_temperature_unit()

    @property
    @override
    def min_temp(self) -> float:
        """Lower end of the target slider."""
        if self._uses_fahrenheit():
            return _MIN_F
        return _MIN_C

    @property
    @override
    def max_temp(self) -> float:
        """Upper end of the target slider."""
        if self._uses_fahrenheit():
            return _MAX_F
        return _MAX_C

    @property
    @override
    def target_temperature_step(self) -> float:
        """Slider step in the sensor unit."""
        if self._uses_fahrenheit():
            return _STEP_F
        return _STEP_C

    @property
    @override
    def target_temperature(self) -> float | None:
        """Local setpoint. None hides it when no sensor is configured."""
        if not self._thermostat_available:
            return None
        return self._target_temperature

    @property
    @override
    def hvac_mode(self) -> HVACMode:
        """Stored mode while a sensor is set, otherwise the device flags."""
        if self._thermostat_available and self._requested_mode is not None:
            return self._requested_mode
        return self._mode_from_device()

    @property
    @override
    def hvac_action(self) -> HVACAction:
        """Cooling when the pump is on. Idle when Cool is holding the target."""
        if self.data.pump_on:
            return HVACAction.COOLING
        mode = self.hvac_mode
        if mode == HVACMode.COOL and self._thermostat_available:
            return HVACAction.IDLE
        if self.data.fan_on:
            return HVACAction.FAN
        return HVACAction.OFF

    @property
    @override
    def fan_mode(self) -> str:
        """Return the current speed, or the last one while the unit is off."""
        speed = self.data.speed if self.data.fan_on else self.data.last_speed
        return str(max(1, min(SPEED_MAX, speed or 1)))

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set off, fan only, or cool.

        Off stops the fan and the pump. The courtesy light is left alone.
        With a room sensor, Cool starts the fan and lets the pump follow the target.
        """
        async with self._control_lock:
            if hvac_mode == HVACMode.OFF:
                if self.hvac_mode != HVACMode.OFF:
                    self._last_running_mode = self.hvac_mode
                self._requested_mode = HVACMode.OFF
                self._saw_fan_on = False
                self.async_write_ha_state()
                await self.coordinator.async_set_power(
                    fan_on=False, speed=0, pump_on=False
                )
            else:
                self._last_running_mode = hvac_mode
                self._requested_mode = hvac_mode
                self.async_write_ha_state()
                speed = self._clamped_speed(None)
                if hvac_mode == HVACMode.FAN_ONLY:
                    self._saw_fan_on = True
                    await self.coordinator.async_set_power(
                        fan_on=True, speed=speed, pump_on=False
                    )
                elif not self._thermostat_available:
                    self._saw_fan_on = True
                    await self.coordinator.async_set_power(
                        fan_on=True, speed=speed, pump_on=True
                    )
                else:
                    await self._async_write_thermostat(ensure_fan=True)
        self._finish_thermostat()

    @override
    async def async_turn_on(self) -> None:
        """Restore the last running mode."""
        mode = self._last_running_mode
        if mode == HVACMode.OFF:
            mode = HVACMode.FAN_ONLY
        await self.async_set_hvac_mode(mode)

    @override
    async def async_turn_off(self) -> None:
        """Turn the unit off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @override
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set speed 1-10. Off plus a speed starts fan only and leaves the pump off."""
        speed = max(1, min(SPEED_MAX, int(fan_mode)))
        async with self._control_lock:
            if self._thermostat_available and self._requested_mode == HVACMode.COOL:
                await self._async_write_thermostat(ensure_fan=True, speed=speed)
            else:
                if (
                    self._thermostat_available
                    and self._requested_mode == HVACMode.OFF
                ):
                    self._requested_mode = HVACMode.FAN_ONLY
                    self._last_running_mode = HVACMode.FAN_ONLY
                    self.async_write_ha_state()
                if self.data.fan_on:
                    await self.coordinator.async_set_power(speed=speed)
                else:
                    self._saw_fan_on = True
                    await self.coordinator.async_set_power(
                        fan_on=True, speed=speed, pump_on=False
                    )
        self._finish_thermostat()

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Store a target and cycle the pump when Cool is selected."""
        if not self._thermostat_available:
            return
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        async with self._control_lock:
            temperature = kwargs.get(ATTR_TEMPERATURE)
            if temperature is not None:
                self._target_temperature = min(
                    self.max_temp, max(self.min_temp, float(temperature))
                )
            if hvac_mode is None:
                self.async_write_ha_state()
                if self._requested_mode == HVACMode.COOL:
                    await self._async_write_thermostat()
        if hvac_mode is not None:
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
            return
        self._finish_thermostat()

    async def _async_stop_stranded_pump(self) -> None:
        """Fan already dropped. Don't leave the pump running with no airflow."""
        if self._control_lock.locked():
            return
        async with self._control_lock:
            if self._requested_mode != HVACMode.OFF or self.data.fan_on:
                return
            if not self.data.pump_on:
                return
            await self.coordinator.async_set_power(fan_on=False, speed=0, pump_on=False)

    async def _async_apply_thermostat(self) -> None:
        """Background pump check. A user command in progress wins."""
        if self._control_lock.locked():
            self._thermostat_pending = True
            return
        try:
            async with self._control_lock:
                self._thermostat_pending = False
                await self._async_write_thermostat()
        except Exception:
            _LOGGER.exception("Neil climatizador thermostat failed")
            return
        self._finish_thermostat()

    async def _async_write_thermostat(
        self,
        *,
        ensure_fan: bool = False,
        speed: int | None = None,
    ) -> None:
        """Cycle the pump. Caller holds the control lock.

        The fan stays on while Cool is holding the target. It starts when
        the pump should run, or when the user just selected Cool.
        """
        if self._requested_mode != HVACMode.COOL or not self._thermostat_available:
            return
        if self._target_is_minimum():
            await self._async_hold_pump(ensure_fan=ensure_fan, speed=speed)
            return
        current = self._room_temperature()
        target = self._target_temperature
        if current is None or target is None:
            if ensure_fan and not self.data.fan_on:
                self._saw_fan_on = True
                await self.coordinator.async_set_power(
                    fan_on=True,
                    speed=self._clamped_speed(speed),
                    pump_on=True,
                )
            return
        want_pump = self._want_pump(current, target)
        fan_on = self.data.fan_on
        if not fan_on and not ensure_fan and not want_pump:
            return
        desired_speed = self._clamped_speed(speed)
        if (
            fan_on
            and self.data.pump_on == want_pump
            and (speed is None or self.data.speed == desired_speed)
        ):
            return
        self._saw_fan_on = True
        if fan_on and speed is None:
            await self.coordinator.async_set_power(pump_on=want_pump)
            return
        await self.coordinator.async_set_power(
            fan_on=True,
            speed=desired_speed,
            pump_on=want_pump,
        )

    async def _async_hold_pump(
        self,
        *,
        ensure_fan: bool,
        speed: int | None,
    ) -> None:
        """Minimum target. Leave the pump unless the user just selected Cool.

        Caller holds the control lock. A speed change keeps the current pump.
        Selecting Cool turns the fan and the pump on, then nothing cycles them.
        """
        if not ensure_fan and speed is None:
            return
        self._saw_fan_on = True
        desired_speed = self._clamped_speed(speed)
        if speed is None:
            await self.coordinator.async_set_power(
                fan_on=True,
                speed=desired_speed,
                pump_on=True,
            )
            return
        if self.data.fan_on:
            await self.coordinator.async_set_power(speed=desired_speed)
            return
        await self.coordinator.async_set_power(
            fan_on=True,
            speed=desired_speed,
            pump_on=self.data.pump_on,
        )
