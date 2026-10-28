"""Diagnostic sensors. Values are raw protocol bytes."""

from __future__ import annotations

from typing import override

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    """Byte 5 of a power status frame. 0 is empty, 1 means the tank has water.

    Neil Connect 2.2.0 stores this byte and never displays it. Live values on
    the Camper have only been 0 and 1.
    """

    _attr_translation_key = "water"
    _attr_name = "Water level"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["empty", "has_water"]

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_water"

    @property
    @override
    def native_value(self) -> str | None:
        """Map the water byte. Anything other than 0 or 1 is unknown."""
        if self.data.water_level == 0:
            return "empty"
        if self.data.water_level == 1:
            return "has_water"
        return None

    @property
    @override
    def icon(self) -> str:
        """Drop icon when the tank reads empty."""
        if self.native_value == "has_water":
            return "mdi:water"
        return "mdi:water-off"


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
