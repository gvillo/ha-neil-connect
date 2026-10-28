"""Timer setpoint. 0 turns the timer off. 1–5 are the app's hour steps."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    TIMER_HOURS_MAX,
    TIMER_HOURS_MIN,
    UPDATE_INTERVAL_SECONDS,
)
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the timer hours box and the poll interval."""
    coordinator = entry.runtime_data
    async_add_entities([NeilTimerHours(coordinator), NeilPollInterval(coordinator)])


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


class NeilPollInterval(NeilEntity, NumberEntity, RestoreEntity):
    """How often status is read, in seconds. Default is 60."""

    _attr_translation_key = "poll_interval"
    _attr_name = "Poll interval"
    _attr_icon = "mdi:timer-sync"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = POLL_INTERVAL_MIN
    _attr_native_max_value = POLL_INTERVAL_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_poll_interval"
        self._seconds = UPDATE_INTERVAL_SECONDS

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last interval and reschedule the poll."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._seconds = _clamp_poll_interval(float(last.state))
            except ValueError:
                self._seconds = UPDATE_INTERVAL_SECONDS
        self.coordinator.set_poll_interval(self._seconds)
        self.async_write_ha_state()

    @property
    @override
    def native_value(self) -> int:
        """Current poll interval in seconds."""
        return self._seconds

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Store the interval and reschedule the status poll."""
        self._seconds = _clamp_poll_interval(value)
        self.coordinator.set_poll_interval(self._seconds)
        self.async_write_ha_state()


def _clamp_poll_interval(seconds: float) -> int:
    """Keep the poll between 10 s and 1 h."""
    return max(POLL_INTERVAL_MIN, min(POLL_INTERVAL_MAX, int(seconds)))
