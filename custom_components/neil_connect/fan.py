"""Fan entity for a Neil climatizador."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SPEED_MAX
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the fan."""
    async_add_entities([NeilFan(entry.runtime_data)])


class NeilFan(NeilEntity, FanEntity):
    """On/off and 10 speed steps. Off does not clear the pump or the light."""

    _attr_name = None
    _attr_speed_count = 10
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_fan"

    @property
    @override
    def is_on(self) -> bool:
        """Return the fan flag. Speed 0 is off only when that flag is clear."""
        return self.data.fan_on

    @property
    @override
    def percentage(self) -> int:
        """Map speed 0-10 onto 0-100 in steps of 10."""
        if not self.data.fan_on:
            return 0
        return max(0, min(100, self.data.speed * 10))

    @override
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on. Restore the last speed, at least 1."""
        if percentage:
            speed = max(1, min(SPEED_MAX, percentage // 10))
        else:
            speed = max(1, self.data.last_speed)
        await self.coordinator.async_set_power(fan_on=True, speed=speed)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send fan 0 and speed 0. Pump and light stay as they are."""
        await self.coordinator.async_set_power(fan_on=False, speed=0)

    @override
    async def async_set_percentage(self, percentage: int) -> None:
        """Set a 10% step, or turn the fan off at 0%."""
        if percentage == 0:
            await self.async_turn_off()
            return
        speed = max(1, min(SPEED_MAX, percentage // 10))
        await self.coordinator.async_set_power(fan_on=True, speed=speed)
