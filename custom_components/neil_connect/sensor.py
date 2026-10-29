"""Sensors.

Water and the timer are protocol bytes. Signal strength is scanner RSSI.
Maintenance hours are counted locally while the fan is on.
"""

from __future__ import annotations

from typing import override

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FILTER_INTERVAL_HOURS, SERVICE_INTERVAL_HOURS
from .coordinator import NeilConfigEntry, NeilCoordinator, NeilEntity
from .maintenance import NeilMaintenanceEntity, hours_left, interval_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add water, timer, signal, and the local runtime counters."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NeilWaterSensor(coordinator),
            NeilTimerRemainingSensor(coordinator),
            NeilSignalStrengthSensor(coordinator),
            NeilOperatingHoursSensor(coordinator),
            NeilServiceHoursSensor(coordinator),
            NeilFilterHoursSensor(coordinator),
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


class NeilDurationSensor(NeilMaintenanceEntity, SensorEntity):
    """Fan hours, counted locally."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1


class NeilRuntimeSensor(NeilDurationSensor):
    """A fan-hour total. Resets are meter resets for statistics."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING


class NeilOperatingHoursSensor(NeilRuntimeSensor):
    """Hours the fan has run since this integration started counting."""

    _attr_translation_key = "operating_hours"
    _attr_name = "Operating hours"
    _attr_icon = "mdi:fan-clock"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_operating_hours"

    @property
    @override
    def native_value(self) -> float:
        """Lifetime fan hours."""
        return self.maintenance.operating_hours


class NeilCountdownSensor(NeilDurationSensor):
    """Hours left until a maintenance interval. Counts down."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @override
    async def async_added_to_hass(self) -> None:
        """Restore hours. Home Assistant kept days from the previous unit."""
        await super().async_added_to_hass()
        registry_entry = self.registry_entry
        if registry_entry is None:
            return
        private = registry_entry.options.get("sensor.private", {})
        if private.get("suggested_unit_of_measurement") in (None, UnitOfTime.HOURS):
            return
        self.registry_entry = er.async_get(self.hass).async_update_entity_options(
            registry_entry.entity_id,
            "sensor.private",
            {"suggested_unit_of_measurement": UnitOfTime.HOURS},
        )


class NeilServiceHoursSensor(NeilCountdownSensor):
    """Time left until the 300 h service."""

    _attr_translation_key = "service_hours"
    _attr_name = "Maintenance remaining"
    _attr_icon = "mdi:wrench-clock"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_service_hours"

    @property
    @override
    def native_value(self) -> float:
        """300 h minus fan time since the last maintenance reset."""
        return hours_left(self.maintenance.service_hours, SERVICE_INTERVAL_HOURS)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, float | int | bool | str]:
        """Interval, hours already used, whether the repair is open, and the links."""
        return interval_attributes(self.maintenance.service_hours, SERVICE_INTERVAL_HOURS)


class NeilFilterHoursSensor(NeilCountdownSensor):
    """Time left until the evaporator filter is replaced."""

    _attr_translation_key = "filter_hours"
    _attr_name = "Filter remaining"
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Set the unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_filter_hours"

    @property
    @override
    def native_value(self) -> float:
        """900 h minus fan time since the last filter reset."""
        return hours_left(self.maintenance.filter_hours, FILTER_INTERVAL_HOURS)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, float | int | bool | str]:
        """Interval, hours already used, whether the repair is open, and the links."""
        return interval_attributes(self.maintenance.filter_hours, FILTER_INTERVAL_HOURS)
