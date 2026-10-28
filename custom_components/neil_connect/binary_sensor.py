"""Due flags for the 300 h service and the 900 h evaporator filter."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FILTER_INTERVAL_HOURS, SERVICE_INTERVAL_HOURS
from .coordinator import NeilConfigEntry, NeilCoordinator
from .maintenance import NeilMaintenanceEntity, interval_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the maintenance and filter alerts."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NeilServiceDueBinarySensor(coordinator),
            NeilFilterDueBinarySensor(coordinator),
        ]
    )


class NeilServiceDueBinarySensor(NeilMaintenanceEntity, BinarySensorEntity):
    """On at 300 fan hours since the last preventive maintenance."""

    _attr_translation_key = "service_due"
    _attr_name = "Service"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_service_due"

    @property
    @override
    def is_on(self) -> bool:
        """True when the 300 h service is due."""
        return self.maintenance.service_due

    @property
    @override
    def icon(self) -> str:
        """Alert icon while the service is due."""
        if self.is_on:
            return "mdi:wrench-alert"
        return "mdi:wrench"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, float | int | bool | str]:
        """Hours counted toward the 300 h interval, plus the manual links."""
        return interval_attributes(self.maintenance.service_hours, SERVICE_INTERVAL_HOURS)


class NeilFilterDueBinarySensor(NeilMaintenanceEntity, BinarySensorEntity):
    """On at 900 fan hours since the evaporator filter was replaced."""

    _attr_translation_key = "filter_due"
    _attr_name = "Evaporator filter"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_filter_due"

    @property
    @override
    def is_on(self) -> bool:
        """True when the filter should be replaced."""
        return self.maintenance.filter_due

    @property
    @override
    def icon(self) -> str:
        """Alert icon while the filter is due."""
        if self.is_on:
            return "mdi:alert"
        return "mdi:air-filter"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, float | int | bool | str]:
        """Hours counted toward the 900 h interval, plus the manual links."""
        return interval_attributes(self.maintenance.filter_hours, FILTER_INTERVAL_HOURS)
