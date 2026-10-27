"""Climate entity for a Neil climatizador.

The protocol has no temperature setpoint. Modes are the fan and the
evaporative pump, the same split an air conditioner uses for fan-only and cool.
"""

from __future__ import annotations

from typing import override

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_TEMPERATURE_SENSOR, SPEED_MAX
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity

FAN_MODES = [str(speed) for speed in range(1, SPEED_MAX + 1)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the climate entity."""
    async_add_entities([NeilClimate(entry.runtime_data)])


class NeilClimate(NeilEntity, ClimateEntity):
    """Off, fan only, or cool. Fan speeds are 1-10."""

    _attr_translation_key = "climatizador"
    _attr_name = "Climatizador"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.COOL]
    _attr_fan_modes = FAN_MODES
    _attr_supported_features = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id and remember the last running mode."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_climate"
        self._last_running_mode = HVACMode.FAN_ONLY

    @override
    async def async_added_to_hass(self) -> None:
        """Refresh the card when the chosen room sensor changes."""
        await super().async_added_to_hass()
        entity_id = self._temperature_entity_id()
        if entity_id is None:
            return
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [entity_id], self._async_temperature_changed
            )
        )

    @callback
    def _async_temperature_changed(self, _event: Event) -> None:
        """The room sensor moved. The climatizador did not."""
        self.async_write_ha_state()

    def _temperature_entity_id(self) -> str | None:
        """Return the optional sensor selected in the integration options."""
        entity_id = self.coordinator.entry.options.get(CONF_TEMPERATURE_SENSOR)
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
    def hvac_mode(self) -> HVACMode:
        """Map fan and pump flags onto off, fan only, or cool."""
        if not self.data.fan_on:
            return HVACMode.OFF
        if self.data.pump_on:
            return HVACMode.COOL
        return HVACMode.FAN_ONLY

    @property
    @override
    def hvac_action(self) -> HVACAction:
        """Report what the unit is doing. There is no thermostat."""
        mode = self.hvac_mode
        if mode == HVACMode.COOL:
            return HVACAction.COOLING
        if mode == HVACMode.FAN_ONLY:
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
        """
        if hvac_mode == HVACMode.OFF:
            if self.hvac_mode != HVACMode.OFF:
                self._last_running_mode = self.hvac_mode
            await self.coordinator.async_set_power(
                fan_on=False, speed=0, pump_on=False
            )
            return
        self._last_running_mode = hvac_mode
        await self.coordinator.async_set_power(
            fan_on=True,
            speed=max(1, self.data.last_speed),
            pump_on=hvac_mode == HVACMode.COOL,
        )

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
        """Set speed 1-10. Turning the speed on while off does not start the pump."""
        speed = max(1, min(SPEED_MAX, int(fan_mode)))
        if self.data.fan_on:
            await self.coordinator.async_set_power(speed=speed)
            return
        await self.coordinator.async_set_power(fan_on=True, speed=speed, pump_on=False)
