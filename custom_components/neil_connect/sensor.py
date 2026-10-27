"""Diagnostic sensors. Values are raw protocol bytes."""

from __future__ import annotations

from typing import override

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add water level and timer remaining."""
    coordinator = entry.runtime_data
    async_add_entities(
        [NeilWaterSensor(coordinator), NeilTimerRemainingSensor(coordinator)]
    )


class NeilWaterSensor(NeilEntity, SensorEntity):
    """Byte 5 of the power frame. No scale."""

    _attr_translation_key = "water"
    _attr_name = "Water level"
    _attr_icon = "mdi:water"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_water"

    @property
    @override
    def native_value(self) -> int:
        """Return the raw water byte."""
        return self.data.water_level


class NeilTimerRemainingSensor(NeilEntity, SensorEntity):
    """Timer byte 3, currentHours. The scale is unverified."""

    _attr_translation_key = "timer_remaining"
    _attr_name = "Timer remaining hours"
    _attr_icon = "mdi:timer-sand"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_timer_remaining"

    @property
    @override
    def native_value(self) -> int:
        """Return the raw remaining-hours byte."""
        return self.data.timer_remaining_hours
