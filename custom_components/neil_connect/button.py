"""Reset the maintenance counters after the work is done."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NeilConfigEntry, NeilCoordinator
from .maintenance import NeilMaintenanceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the service and filter reset buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NeilResetServiceButton(coordinator),
            NeilResetFilterButton(coordinator),
        ]
    )


class NeilResetServiceButton(NeilMaintenanceEntity, ButtonEntity):
    """Zero the 300 h counter. The filter counter stays."""

    _attr_translation_key = "reset_service"
    _attr_name = "Reset preventive maintenance"
    _attr_icon = "mdi:backup-restore"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_reset_service"

    @override
    async def async_press(self) -> None:
        """The 300 h service is done."""
        await self.maintenance.async_reset_service()


class NeilResetFilterButton(NeilMaintenanceEntity, ButtonEntity):
    """Zero the 900 h counter and the 300 h counter.

    Replacing the evaporator filter is part of that same service.
    """

    _attr_translation_key = "reset_filter"
    _attr_name = "Reset filter and service"
    _attr_icon = "mdi:backup-restore"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_reset_filter"

    @override
    async def async_press(self) -> None:
        """The filter was replaced and the 300 h service was done."""
        await self.maintenance.async_reset_filter()
