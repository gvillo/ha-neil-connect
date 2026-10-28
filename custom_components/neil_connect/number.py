"""Timer setpoint, and boxes to correct the maintenance counters.

The timer is 0 off, or 1–5 hours. The maintenance boxes overwrite the local
fan-hour counters when the unit is not new.
"""

from __future__ import annotations

from typing import override

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import TIMER_HOURS_MAX, TIMER_HOURS_MIN
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity
from .maintenance import NeilMaintenanceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the timer and the maintenance hour corrections."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NeilTimerHours(coordinator),
            NeilServiceHoursAdjustment(coordinator),
            NeilFilterHoursAdjustment(coordinator),
        ]
    )


class NeilTimerHours(NeilEntity, NumberEntity):
    """Selected timer hours. Zero sends timer off."""

    _attr_translation_key = "timer_hours"
    _attr_name = "Timer hours"
    _attr_icon = "mdi:timer-cog"
    _attr_native_min_value = TIMER_HOURS_MIN
    _attr_native_max_value = TIMER_HOURS_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_timer_hours"

    @property
    @override
    def native_value(self) -> int:
        """Return 0 when the timer is off, otherwise the selected hour."""
        if not self.data.timer_on:
            return 0
        hours = self.data.timer_selected_hours
        if hours < 1 or hours > TIMER_HOURS_MAX:
            return 0
        return hours

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Send timer on at 1–5 hours, or timer off for 0."""
        hours = int(value)
        if hours <= 0:
            await self.coordinator.async_set_timer(False, 0)
            return
        if hours > TIMER_HOURS_MAX:
            hours = TIMER_HOURS_MAX
        await self.coordinator.async_set_timer(True, hours)


class NeilHourAdjustment(NeilMaintenanceEntity, NumberEntity):
    """Overwrite one counter. The unit may already have hours on it."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_min_value = 0
    _attr_native_max_value = 100_000
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX


class NeilServiceHoursAdjustment(NeilHourAdjustment):
    """Set hours since the last preventive maintenance."""

    _attr_translation_key = "service_hours_adjust"
    _attr_name = "Adjust service hours"
    _attr_icon = "mdi:wrench"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_service_hours_adjust"

    @property
    @override
    def native_value(self) -> float:
        """Hours currently counted toward the 300 h service."""
        return self.maintenance.service_hours

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Replace the 300 h counter."""
        await self.maintenance.async_set_service_hours(value)


class NeilFilterHoursAdjustment(NeilHourAdjustment):
    """Set hours since the evaporator filter was replaced."""

    _attr_translation_key = "filter_hours_adjust"
    _attr_name = "Adjust filter hours"
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_filter_hours_adjust"

    @property
    @override
    def native_value(self) -> float:
        """Hours currently counted toward the 900 h filter."""
        return self.maintenance.filter_hours

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Replace the 900 h counter. The service counter is left alone."""
        await self.maintenance.async_set_filter_hours(value)
