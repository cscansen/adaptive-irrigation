from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.dt import parse_datetime

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
        ETSensor(coordinator, zone),
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
        return self.coordinator.data.get("moisture") if self.coordinator.data else None


class TrendSensor(_ZoneBase, SensorEntity):
    _attr_native_unit_of_measurement = "%/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "trend")
        self._attr_name = "Moisture Trend"

    @property
    def native_value(self):
        return self.coordinator.data.get("trend") if self.coordinator.data else None


class ETSensor(_ZoneBase, SensorEntity):
    _attr_native_unit_of_measurement = "mm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-sunny"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "et_today")
        self._attr_name = "ET Today"

    @property
    def native_value(self):
        return self.coordinator.data.get("et_today") if self.coordinator.data else None


class StatusSensor(_ZoneBase, SensorEntity):
    _attr_icon = "mdi:sprinkler"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "status")
        self._attr_name = "Status"

    @property
    def native_value(self) -> str:
        return (self.coordinator.data.get("status") or "Idle") if self.coordinator.data else "Idle"


class LastWateredSensor(_ZoneBase, RestoreEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "last_watered")
        self._attr_name = "Last Watered"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", "None", "none"):
            dt = parse_datetime(last.state)
            if dt:
                self.coordinator.set_last_watered(dt)

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.get("last_watered") if self.coordinator.data else None


class CalibrationSensor(_ZoneBase, RestoreEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%/min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:tune"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "calibration")
        self._attr_name = "Calibration Rate"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", "None", "none"):
            try:
                self.coordinator.set_calibration(float(last.state))
            except ValueError:
                pass

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("calibration") if self.coordinator.data else None
