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

from .const import CONF_SOIL_TEMP_SENSOR, DEFAULT_WEATHER_ENTITY, DOMAIN, ENTRY_TYPE_SYSTEM
from .coordinator import AdaptiveIrrigationCoordinator

_CONFIG_DEVICE = {
    "identifiers": {(DOMAIN, "configuration")},
    "name": "Configuration",
    "manufacturer": "adaptive_irrigation",
}

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_type = entry.data.get("entry_type")
    domain_data = hass.data.get(DOMAIN, {})

    if entry_type == ENTRY_TYPE_SYSTEM:
        async_add_entities([DailyUsedSensor(hass), WeatherSourceSensor(hass)])
        return

    coordinator: AdaptiveIrrigationCoordinator = domain_data[entry.entry_id]
    zone = coordinator.zone_name
    entities = [
        MoistureSensor(coordinator, zone),
        TrendSensor(coordinator, zone),
        ETSensor(coordinator, zone),
        ForecastPrecipSensor(coordinator, zone),
        ForecastWindSensor(coordinator, zone),
        StatusSensor(coordinator, zone),
        LastWateredSensor(coordinator, zone),
        CalibrationSensor(coordinator, zone),
        DaysToRefillSensor(coordinator, zone),
    ]
    # Heat-stress entities only exist where a root-zone probe is configured.
    if coordinator.config.get(CONF_SOIL_TEMP_SENSOR):
        entities.extend([
            SoilTemperatureSensor(coordinator, zone),
            CoolingRunsTodaySensor(coordinator, zone),
            CoolingDeltaSensor(coordinator, zone),
            LastCooledSensor(coordinator, zone),
        ])
    # Legacy backward-compat
    if "system_entry_id" not in domain_data and not domain_data.get("system_sensor_added"):
        domain_data["system_sensor_added"] = True
        entities.extend([DailyUsedSensor(hass), WeatherSourceSensor(hass)])
    async_add_entities(entities)


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


class ForecastPrecipSensor(_ZoneBase, SensorEntity):
    _attr_native_unit_of_measurement = "in"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-rainy"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "forecast_precip")
        self._attr_name = "Rain Forecast"

    @property
    def native_value(self):
        return self.coordinator.data.get("precip") if self.coordinator.data else None


class ForecastWindSensor(_ZoneBase, SensorEntity):
    _attr_native_unit_of_measurement = "mph"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-windy"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "forecast_wind")
        self._attr_name = "Wind Forecast"

    @property
    def native_value(self):
        return self.coordinator.data.get("wind") if self.coordinator.data else None


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


class DailyUsedSensor(SensorEntity):
    """System-level daily water usage — reads from Flume meter delta or accumulated estimate."""

    _attr_unique_id = "adaptive_irrigation_daily_used"
    _attr_name = "Daily Water Used"
    _attr_native_unit_of_measurement = "gal"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = False

    def __init__(self, hass) -> None:
        self._hass = hass

    @property
    def device_info(self):
        return _CONFIG_DEVICE

    @property
    def native_value(self) -> float:
        domain_data = self._hass.data.get(DOMAIN, {})
        # Don't report yesterday's total. The rollover used to depend entirely
        # on a zone coordinator polling after midnight; if that didn't happen
        # the figure simply stuck (observed: frozen at 48.0 for 14 hours with a
        # single recorder point).
        from homeassistant.util import dt as _dt
        if domain_data.get("budget_date") != _dt.now().date().isoformat():
            return 0.0
        meter_entity = domain_data.get("water_meter_entity")
        if meter_entity:
            state = self._hass.states.get(meter_entity)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    current = float(state.state)
                    baseline = domain_data.get("water_meter_baseline", current)
                    return round(max(0.0, current - baseline), 1)
                except ValueError:
                    pass
        return round(domain_data.get("daily_used_gallons", 0.0), 1)


class WeatherSourceSensor(SensorEntity):
    """Shows which weather entity the integration is currently using."""

    _attr_unique_id = "adaptive_irrigation_weather_source"
    _attr_name = "Weather Source"
    _attr_icon = "mdi:weather-partly-cloudy"
    _attr_has_entity_name = False

    def __init__(self, hass) -> None:
        self._hass = hass

    @property
    def device_info(self):
        return _CONFIG_DEVICE

    @property
    def native_value(self) -> str:
        return self._hass.data.get(DOMAIN, {}).get("weather_entity", DEFAULT_WEATHER_ENTITY)


class DaysToRefillSensor(_ZoneBase, SensorEntity):
    """Projected days until the zone reaches its refill point.

    This is what ET is for under the interval-adaptive model: predicting when
    the next soak falls due, rather than inflating the fill target.
    """

    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "days_to_refill")
        self._attr_name = "Days To Refill"

    @property
    def native_value(self):
        return self.coordinator.data.get("days_to_refill") if self.coordinator.data else None


class SoilTemperatureSensor(_ZoneBase, SensorEntity):
    """Root-zone temperature as the integration sees it.

    Surfaced on the zone device because it drives every cooling decision, and
    because it is the most important number about a sun-exposed lawn.
    """

    _attr_native_unit_of_measurement = "°F"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "soil_temp")
        self._attr_name = "Root Zone Temperature"

    @property
    def native_value(self):
        return self.coordinator.data.get("soil_temp") if self.coordinator.data else None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        rise = data.get("soil_temp_rise")
        return {
            "rise_rate_f_per_hour": round(rise * 60, 2) if rise is not None else None,
            "cooling_status": data.get("cooling_status"),
        }


class CoolingRunsTodaySensor(_ZoneBase, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "cooling_runs_today")
        self._attr_name = "Cooling Runs Today"

    @property
    def native_value(self):
        return self.coordinator.data.get("cooling_runs_today") if self.coordinator.data else None


class CoolingDeltaSensor(_ZoneBase, SensorEntity):
    """Temperature change achieved by the most recent cooling run.

    Makes "did that actually help?" answerable per zone instead of assumed —
    a run that rebounds straight past its starting temperature is a run that
    needs retiming, not repeating.
    """

    _attr_native_unit_of_measurement = "°F"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-minus"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "cooling_delta")
        self._attr_name = "Last Cooling Delta"

    @property
    def native_value(self):
        return self.coordinator.data.get("last_cooling_delta") if self.coordinator.data else None


class LastCooledSensor(_ZoneBase, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "last_cooling")
        self._attr_name = "Last Cooled"

    @property
    def native_value(self):
        return self.coordinator.data.get("last_cooling") if self.coordinator.data else None
