"""Fan-runtime counters for the Camper maintenance schedule.

The peripheral does not report hours. Time counts while the fan is on and
polls keep arriving. A gap longer than five minutes is dropped, so a BLE
outage or a Home Assistant restart is not counted as use.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging
import time
from typing import override

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_TITLE,
    DOMAIN,
    FILTER_INTERVAL_HOURS,
    MANUAL_URL,
    MAINTENANCE_URL,
    SERVICE_INTERVAL_HOURS,
)
from .coordinator import NeilCoordinator, NeilEntity

_LOGGER = logging.getLogger(__name__)

# One missed poll is 30 s. Five minutes still counts. Longer than that is an
# outage, and the fan may have been turned off on the remote.
_SAMPLE_MAX_SECONDS = 300.0
_SAVE_DELAY_SECONDS = 300.0

_MaintenanceKey = tuple[float, float, float, bool, bool]


def _hours(seconds: float) -> float:
    """One decimal hour. 0.1 h is 6 minutes."""
    return round(seconds / 3600, 1)


def _nonnegative(value: object) -> float:
    """Stored JSON numbers only. Anything else is zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, float(value))


def hours_left(elapsed: float, interval: int) -> float:
    """Hours until the interval. Stays at 0 once the work is due."""
    return max(0.0, round(interval - elapsed, 1))


def interval_attributes(
    elapsed: float, interval: int
) -> dict[str, float | int | bool | str]:
    """Shared state attributes for the hour sensors and the due flags."""
    return {
        "interval_hours": interval,
        "hours_used": elapsed,
        "due": elapsed >= interval,
        "manual_url": MANUAL_URL,
        "maintenance_url": MAINTENANCE_URL,
    }


def _storage_token(address: str) -> str:
    """A store key segment. BLE addresses contain colons."""
    return "".join(char.lower() if char.isalnum() else "_" for char in address)


class NeilMaintenance:
    """Three counters: lifetime, since the 300 h service, since the 900 h filter."""

    def __init__(self, hass: HomeAssistant, coordinator: NeilCoordinator) -> None:
        """Bind storage to this peripheral."""
        self.hass = hass
        entry = coordinator.config_entry
        self._title = entry.title if entry is not None else DEFAULT_TITLE
        self._address = coordinator.address
        token = _storage_token(coordinator.address)
        self._store: Store[dict[str, float]] = Store(
            hass, 1, f"{DOMAIN}_maintenance_{token}"
        )
        self.total_seconds = 0.0
        self.service_seconds = 0.0
        self.filter_seconds = 0.0
        self._anchor: float | None = None
        self._fan_on = False
        self._listeners: set[Callable[[], None]] = set()
        self._published: _MaintenanceKey | None = None
        self._service_open = False
        self._filter_open = False
        self._issues_ready = False
        self._closed = False
        self._save_lock = asyncio.Lock()
        self._save_unsub: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Load the counters and raise a repair if one is already due."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self.total_seconds = _nonnegative(stored.get("total_seconds"))
            self.service_seconds = _nonnegative(stored.get("service_seconds"))
            self.filter_seconds = _nonnegative(stored.get("filter_seconds"))
        self._sync_issues(announce=False)
        self._published = self._key()

    async def async_shutdown(self) -> None:
        """Persist and stop. A later poll must not overwrite this write."""
        self._closed = True
        self._cancel_save()
        async with self._save_lock:
            await self._async_write_locked()

    def observe(self, fan_on: bool) -> None:
        """Add the time since the previous sample when the fan stayed on."""
        if self._closed:
            return
        now = time.monotonic()
        anchor = self._anchor
        was_on = self._fan_on
        self._anchor = now
        self._fan_on = fan_on
        if anchor is None or not was_on:
            return
        delta = now - anchor
        if delta <= 0:
            return
        if delta > _SAMPLE_MAX_SECONDS:
            _LOGGER.debug(
                "Dropping %.0f s of runtime for %s after a poll gap",
                delta,
                self._address,
            )
            return
        self.total_seconds += delta
        self.service_seconds += delta
        self.filter_seconds += delta
        if self._publish(announce=True):
            self.hass.async_create_task(
                self._async_write(),
                name="neil_connect maintenance save",
            )
            return
        self._async_schedule_save()

    async def async_reset_service(self) -> None:
        """Zero the 300 h counter. The filter counter stays."""
        if self._closed:
            return
        self.service_seconds = 0.0
        self._publish(announce=False)
        await self._async_write()

    async def async_reset_filter(self) -> None:
        """Zero both counters. The 900 h job includes the 300 h service."""
        if self._closed:
            return
        self.filter_seconds = 0.0
        self.service_seconds = 0.0
        self._publish(announce=False)
        await self._async_write()

    def async_add_listener(
        self, update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Notify when the displayed hours or a due flag changes."""
        self._listeners.add(update_callback)

        @callback
        def remove() -> None:
            self._listeners.discard(update_callback)

        return remove

    @property
    def operating_hours(self) -> float:
        """Fan hours since counting started."""
        return _hours(self.total_seconds)

    @property
    def service_hours(self) -> float:
        """Fan hours since the last preventive maintenance."""
        return _hours(self.service_seconds)

    @property
    def filter_hours(self) -> float:
        """Fan hours since the evaporator filter was replaced."""
        return _hours(self.filter_seconds)

    @property
    def service_due(self) -> bool:
        """True at 300.0 displayed hours."""
        return self.service_hours >= SERVICE_INTERVAL_HOURS

    @property
    def filter_due(self) -> bool:
        """True at 900.0 displayed hours."""
        return self.filter_hours >= FILTER_INTERVAL_HOURS

    def _key(self) -> _MaintenanceKey:
        """Tenths of an hour. A 30 s poll is not a state change."""
        return (
            self.operating_hours,
            self.service_hours,
            self.filter_hours,
            self.service_due,
            self.filter_due,
        )

    def _publish(self, *, announce: bool) -> bool:
        """Push entity state and repairs. True when a due flag flipped."""
        before = (self._service_open, self._filter_open)
        self._sync_issues(announce=announce)
        key = self._key()
        if key != self._published:
            self._published = key
            for listener in list(self._listeners):
                listener()
        return (self._service_open, self._filter_open) != before

    def _sync_issues(self, *, announce: bool) -> None:
        """Create or clear the two repairs."""
        self._service_open = self._sync_issue(
            due=self.service_due,
            kind="service",
            translation_key="service_due",
            was_open=self._service_open,
            announce=announce,
            message="Preventive maintenance is due for %s",
        )
        self._filter_open = self._sync_issue(
            due=self.filter_due,
            kind="filter",
            translation_key="filter_due",
            was_open=self._filter_open,
            announce=announce,
            message="Evaporator filter replacement is due for %s",
        )
        self._issues_ready = True

    def _sync_issue(
        self,
        *,
        due: bool,
        kind: str,
        translation_key: str,
        was_open: bool,
        announce: bool,
        message: str,
    ) -> bool:
        """Return whether the repair should stay open."""
        issue_id = f"{kind}_{_storage_token(self._address)}"
        if due:
            if not was_open:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    is_persistent=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=translation_key,
                    translation_placeholders={"name": self._title},
                    learn_more_url=MAINTENANCE_URL,
                )
                if announce:
                    _LOGGER.warning(message, self._title)
            return True
        if was_open or not self._issues_ready:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        return False

    def _data(self) -> dict[str, float]:
        """Exact seconds. The entities round them for display."""
        return {
            "total_seconds": self.total_seconds,
            "service_seconds": self.service_seconds,
            "filter_seconds": self.filter_seconds,
        }

    def _async_schedule_save(self) -> None:
        """Write at most once per five minutes while the fan runs."""
        if self._closed or self._save_unsub is not None:
            return
        self._save_unsub = async_call_later(
            self.hass, _SAVE_DELAY_SECONDS, self._async_delayed_save
        )

    def _cancel_save(self) -> None:
        """Drop a pending delayed write."""
        unsub = self._save_unsub
        self._save_unsub = None
        if unsub is not None:
            unsub()

    async def _async_delayed_save(self, _now: datetime) -> None:
        """Timer fired. Shutdown may have won the race."""
        self._save_unsub = None
        if self._closed:
            return
        await self._async_write()

    async def _async_write(self) -> None:
        """Save unless shutdown already took the counters."""
        async with self._save_lock:
            if self._closed:
                return
            self._cancel_save()
            await self._async_write_locked()

    async def _async_write_locked(self) -> None:
        """Caller holds the save lock."""
        try:
            await self._store.async_save(self._data())
        except Exception:
            _LOGGER.exception("Could not store maintenance hours for %s", self._address)


class NeilMaintenanceEntity(NeilEntity):
    """Local counter. A BLE outage does not mark it unavailable."""

    def __init__(self, coordinator: NeilCoordinator) -> None:
        """Require the tracker created in async_setup_entry."""
        super().__init__(coordinator)
        maintenance = coordinator.maintenance
        if maintenance is None:
            raise RuntimeError("Neil maintenance tracker is not ready")
        self.maintenance = maintenance

    @property
    @override
    def available(self) -> bool:
        """Hours live in Home Assistant storage, not on the climatizador."""
        return True

    @override
    async def async_added_to_hass(self) -> None:
        """Refresh when the displayed hour or a due flag changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.maintenance.async_add_listener(self._async_maintenance_updated)
        )

    @callback
    def _async_maintenance_updated(self) -> None:
        """The tracker rounded a new hour or opened a repair."""
        self.async_write_ha_state()
