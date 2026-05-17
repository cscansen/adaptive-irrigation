from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdaptiveIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AdaptiveIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    zone = coordinator.zone_name
    async_add_entities([
        MoistureSensor(coordinator, zone),
        TrendSensor(coordinator, zone),
        StatusSensor(coordinator, zone),
        LastWateredSensor(coordinator, zone),
        CalibrationSensor(coordinator, zone),
    ])


class _ZoneBase(CoordinatorEntity[AdaptiveIrrigationCoordinator]):
    def __init__(self, coordinator: AdaptiveIrrigationCoordinator, zone: str, key: str) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"{DOMAIN}_{zone}_{key}"
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._zone)},
            "name": f"Adaptive Irrigation — {self._zone.replace('_', ' ').title()}",
            "manufacturer": "adaptive_irrigation",
        }


class MoistureSensor(_ZoneBase, SensorEntity):
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "moisture")
        self._attr_name = "Moisture"

    @property
    def native_value(self):
        return self.coordinator.data.get("moisture")


class TrendSensor(_ZoneBase, SensorEntity):
    _attr_native_unit_of_measurement = "%/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "trend")
        self._attr_name = "Moisture Trend"

    @property
    def native_value(self):
        return self.coordinator.data.get("trend")


class StatusSensor(_ZoneBase, SensorEntity):
    _attr_icon = "mdi:sprinkler"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "status")
        self._attr_name = "Status"

    @property
    def native_value(self) -> str:
        return "Idle"  # Phase 2 will populate this from watering decisions


class LastWateredSensor(_ZoneBase, RestoreEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "last_watered")
        self._attr_name = "Last Watered"
        self._last_watered: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", "None", "none"):
            try:
                from homeassistant.util.dt import parse_datetime
                self._last_watered = parse_datetime(last.state)
            except Exception:
                pass

    @property
    def native_value(self) -> datetime | None:
        return self._last_watered

    def set_last_watered(self, dt: datetime) -> None:
        self._last_watered = dt
        self.async_write_ha_state()


class CalibrationSensor(_ZoneBase, RestoreEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%/min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:tune"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "calibration")
        self._attr_name = "Calibration Rate"
        self._calibration: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", "None", "none"):
            try:
                self._calibration = float(last.state)
            except ValueError:
                pass

    @property
    def native_value(self) -> float | None:
        return self._calibration

    def update_calibration(self, new_rate: float) -> None:
        if self._calibration is None:
            self._calibration = new_rate
        else:
            # Exponential moving average weighted toward history
            self._calibration = round(0.8 * self._calibration + 0.2 * new_rate, 4)
        self.async_write_ha_state()
