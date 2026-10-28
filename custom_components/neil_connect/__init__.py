"""Neil Connect integration."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import NeilConfigEntry, NeilCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _async_drop_fan_entity(hass: HomeAssistant, entry: NeilConfigEntry) -> None:
    """Remove the fan entity this integration used to create."""
    address = entry.data.get(CONF_ADDRESS)
    if not isinstance(address, str):
        return
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("fan", DOMAIN, f"{address}_fan")
    if entity_id is not None:
        registry.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: NeilConfigEntry) -> bool:
    """Connect, do the first poll, and expose the platforms."""
    coordinator = NeilCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_unload_platforms(entry, [Platform.FAN])
    _async_drop_fan_entity(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: NeilConfigEntry) -> None:
    """Reload when the room temperature sensor changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NeilConfigEntry) -> bool:
    """Unload platforms. The coordinator drops BLE from its shutdown hook."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
