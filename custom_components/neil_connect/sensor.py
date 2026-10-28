"""Sensors. Water and the timer are protocol bytes. Signal strength is scanner RSSI."""

from __future__ import annotations

from typing import override

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add water level, timer remaining, and signal strength."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NeilWaterSensor(coordinator),
            NeilTimerRemainingSensor(coordinator),
            NeilSignalStrengthSensor(coordinator),
        ]
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

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_timer_remaining"

    @override
    async def async_added_to_hass(self) -> None:
        """Drop the diagnostic category this sensor used to have."""
        await super().async_added_to_hass()
        registry_entry = self.registry_entry
        if registry_entry is not None and registry_entry.entity_category is not None:
            er.async_get(self.hass).async_update_entity(
                registry_entry.entity_id,
                entity_category=None,
            )

    @property
    @override
    def native_value(self) -> int:
        """Return the raw remaining-hours byte."""
        return self.data.timer_remaining_hours


class NeilSignalStrengthSensor(NeilEntity, SensorEntity):
    """Scanner RSSI for this peripheral. Disabled until the user enables it."""

    _attr_translation_key = "signal_strength"
    _attr_name = "Signal strength"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_signal_strength"
        self._rssi: int | None = None

    @override
    async def async_added_to_hass(self) -> None:
        """Seed from the last advertisement and follow later ones."""
        info = bluetooth.async_last_service_info(
            self.hass, self.coordinator.address, connectable=True
        )
        if info is not None:
            self._rssi = info.rssi
        await super().async_added_to_hass()
        self.async_on_remove(
            bluetooth.async_register_advertisement_callback(
                self.hass,
                self._async_update_rssi,
                self.coordinator.address,
            )
        )

    @callback
    def _async_update_rssi(self, service_info: BluetoothServiceInfoBleak) -> None:
        """The scanner heard this peripheral again."""
        if service_info.rssi == self._rssi:
            return
        self._rssi = service_info.rssi
        self.async_write_ha_state()

    @property
    @override
    def native_value(self) -> int | None:
        """Last advertisement RSSI. None until the scanner has heard the unit."""
        return self._rssi
