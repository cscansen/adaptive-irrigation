from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DAILY_BUDGET_GALLONS,
    CONF_FLOW_RATE_GPM,
    CONF_MAX_DURATION,
    CONF_SOIL_THRESHOLD,
    CONF_WATER_INTERVAL_DAYS,
    CONF_WINDOW_END_HOUR,
    CONF_WINDOW_START_HOUR,
    DEFAULT_DAILY_BUDGET_GALLONS,
    DEFAULT_FLOW_RATE_GPM,
    DEFAULT_MAX_DURATION,
    DEFAULT_SOIL_THRESHOLD,
    DEFAULT_WATER_INTERVAL_DAYS,
    DEFAULT_WINDOW_END_HOUR,
    DEFAULT_WINDOW_START_HOUR,
    DOMAIN,
)
from .coordinator import AdaptiveIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AdaptiveIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [
        SoilThresholdNumber(coordinator),
        WaterIntervalNumber(coordinator),
        MaxDurationNumber(coordinator),
        FlowRateNumber(coordinator),
    ]
    if not hass.data[DOMAIN].get("system_number_added"):
        hass.data[DOMAIN]["system_number_added"] = True
        entities.extend([
            DailyBudgetNumber(hass),
            WindowStartHourNumber(hass),
            WindowEndHourNumber(hass),
        ])
    async_add_entities(entities)


class _ZoneNumber(CoordinatorEntity[AdaptiveIrrigationCoordinator], RestoreEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: AdaptiveIrrigationCoordinator,
        key: str,
        name: str,
        unit: str,
        min_val: float,
        max_val: float,
        step: float,
        default: float,
    ) -> None:
        super().__init__(coordinator)
        zone = coordinator.zone_name
        self._attr_unique_id = f"{DOMAIN}_{zone}_{key}"
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._current_value: float = float(default)

    @property
    def device_info(self):
        zone = self.coordinator.zone_name
        return {
            "identifiers": {(DOMAIN, zone)},
            "name": f"Adaptive Irrigation — {zone.replace('_', ' ').title()}",
            "manufacturer": "adaptive_irrigation",
        }

    @property
    def native_value(self) -> float:
        return self._current_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            try:
                self._current_value = float(last.state)
            except ValueError:
                pass
        self._push_to_coordinator()

    def _push_to_coordinator(self) -> None:
        raise NotImplementedError

    async def async_set_native_value(self, value: float) -> None:
        self._current_value = value
        self._push_to_coordinator()
        self.async_write_ha_state()


class SoilThresholdNumber(_ZoneNumber):
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_SOIL_THRESHOLD, DEFAULT_SOIL_THRESHOLD)
        super().__init__(coordinator, "soil_threshold", "Soil Threshold", "%", 60.0, 99.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_threshold(self._current_value)


class WaterIntervalNumber(_ZoneNumber):
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_WATER_INTERVAL_DAYS, DEFAULT_WATER_INTERVAL_DAYS)
        super().__init__(coordinator, "water_interval_days", "Water Interval", "d", 1.0, 14.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_water_interval(int(self._current_value))


class MaxDurationNumber(_ZoneNumber):
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_MAX_DURATION, DEFAULT_MAX_DURATION)
        super().__init__(coordinator, "max_duration", "Max Duration", "min", 1.0, 60.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_max_duration(int(self._current_value))




class FlowRateNumber(_ZoneNumber):
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_FLOW_RATE_GPM, DEFAULT_FLOW_RATE_GPM)
        super().__init__(coordinator, "flow_rate_gpm", "Flow Rate", "gal/min", 0.5, 20.0, 0.5, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_flow_rate(self._current_value)


_CONFIG_DEVICE = {
    "identifiers": {(DOMAIN, "configuration")},
    "name": "Configuration",
    "manufacturer": "adaptive_irrigation",
}


class _SystemNumber(RestoreEntity, NumberEntity):
    """Base for system-level number entities that live on the Configuration device."""

    _attr_mode = NumberMode.SLIDER
    _attr_has_entity_name = False

    def __init__(self, hass, default: float) -> None:
        self._hass = hass
        self._current_value: float = default

    @property
    def device_info(self):
        return _CONFIG_DEVICE

    @property
    def native_value(self) -> float:
        return self._current_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            try:
                self._current_value = float(last.state)
            except ValueError:
                pass
        self._push_to_domain()

    def _push_to_domain(self) -> None:
        raise NotImplementedError

    async def async_set_native_value(self, value: float) -> None:
        self._current_value = value
        self._push_to_domain()
        self.async_write_ha_state()


class DailyBudgetNumber(_SystemNumber):
    _attr_icon = "mdi:water-percent"
    _attr_unique_id = "adaptive_irrigation_daily_budget"
    _attr_name = "Daily Water Budget"
    _attr_native_unit_of_measurement = "gal"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 5000.0
    _attr_native_step = 10.0

    def __init__(self, hass) -> None:
        super().__init__(hass, DEFAULT_DAILY_BUDGET_GALLONS)

    def _push_to_domain(self) -> None:
        self._hass.data[DOMAIN]["daily_budget_gallons"] = self._current_value


class WindowStartHourNumber(_SystemNumber):
    _attr_icon = "mdi:clock-start"
    _attr_unique_id = "adaptive_irrigation_window_start_hour"
    _attr_name = "Watering Window Start"
    _attr_native_unit_of_measurement = "hr"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 23.0
    _attr_native_step = 1.0

    def __init__(self, hass) -> None:
        super().__init__(hass, float(DEFAULT_WINDOW_START_HOUR))

    def _push_to_domain(self) -> None:
        self._hass.data[DOMAIN]["window_start_hour"] = int(self._current_value)


class WindowEndHourNumber(_SystemNumber):
    _attr_icon = "mdi:clock-end"
    _attr_unique_id = "adaptive_irrigation_window_end_hour"
    _attr_name = "Watering Window End"
    _attr_native_unit_of_measurement = "hr"
    _attr_native_min_value = 1.0
    _attr_native_max_value = 23.0
    _attr_native_step = 1.0

    def __init__(self, hass) -> None:
        super().__init__(hass, float(DEFAULT_WINDOW_END_HOUR))

    def _push_to_domain(self) -> None:
        self._hass.data[DOMAIN]["window_end_hour"] = int(self._current_value)
