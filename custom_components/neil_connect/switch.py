"""Cooling and light switches. Each one rewrites the full power frame."""

from __future__ import annotations

from typing import override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the pump and light switches."""
    coordinator = entry.runtime_data
    async_add_entities([NeilPumpSwitch(coordinator), NeilLightSwitch(coordinator)])


class NeilPowerSwitch(NeilEntity, SwitchEntity):
    """A boolean in the power frame."""

    _field: str

    def __init__(self, coordinator: NeilCoordinator, suffix: str) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{suffix}"

    async def _async_set(self, value: bool) -> None:
        """Rewrite power with this flag changed and the rest preserved."""
        await self.coordinator.async_set_power(**{self._field: value})


class NeilPumpSwitch(NeilPowerSwitch):
    """Evaporative cool. The app calls this the pump."""

    _attr_translation_key = "pump"
    _attr_name = "Cooling"
    _attr_icon = "mdi:snowflake"
    _field = "pump_on"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator, "pump")

    @property
    @override
    def is_on(self) -> bool:
        """Return the pump flag."""
        return self.data.pump_on

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn cooling on."""
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn cooling off."""
        await self._async_set(False)


class NeilLightSwitch(NeilPowerSwitch):
    """Protocol light bit. The unit has no light, so this starts disabled."""

    _attr_translation_key = "light"
    _attr_name = "Light"
    _attr_icon = "mdi:lightbulb"
    _attr_entity_registry_enabled_default = False
    _field = "bulb_on"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator, "light")

    @property
    @override
    def is_on(self) -> bool:
        """Return the bulb flag."""
        return self.data.bulb_on

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the light on."""
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the light off."""
        await self._async_set(False)
