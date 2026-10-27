"""Neil Connect integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import NeilConfigEntry, NeilCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: NeilConfigEntry) -> bool:
    """Connect, do the first poll, and expose the platforms."""
    coordinator = NeilCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: NeilConfigEntry) -> None:
    """Reload when the room temperature sensor changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NeilConfigEntry) -> bool:
    """Unload platforms. The coordinator drops BLE from its shutdown hook."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
