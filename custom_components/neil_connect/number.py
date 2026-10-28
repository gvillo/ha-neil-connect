"""Timer setpoint. 0 turns the timer off. 1–5 are the app's hour steps."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import TIMER_HOURS_MAX, TIMER_HOURS_MIN
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the timer hours box."""
    async_add_entities([NeilTimerHours(entry.runtime_data)])


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
