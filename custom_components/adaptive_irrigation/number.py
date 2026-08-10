from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_COOLING_DURATION,
    CONF_COOLING_TEMP_THRESHOLD,
    CONF_FALLBACK_DURATION,
    CONF_FILL_TARGET,
    CONF_REFILL_POINT,
    CONF_SOIL_TEMP_SENSOR,
    DEFAULT_COOLING_DURATION,
    DEFAULT_COOLING_TEMP_THRESHOLD,
    DEFAULT_FALLBACK_DURATION,
    DEFAULT_FILL_TARGET,
    DEFAULT_REFILL_POINT,
    CONF_DAILY_BUDGET_GALLONS,
    CONF_FLOW_RATE_GPM,
    CONF_MAX_DURATION,
    CONF_SOAK_CYCLES,
    CONF_SOAK_PAUSE_MINUTES,
    CONF_SOIL_THRESHOLD,
    CONF_WATER_INTERVAL_DAYS,
    DEFAULT_DAILY_BUDGET_GALLONS,
    DEFAULT_FLOW_RATE_GPM,
    DEFAULT_MAX_DURATION,
    DEFAULT_SOAK_CYCLES,
    DEFAULT_SOAK_PAUSE_MINUTES,
    DEFAULT_SOIL_THRESHOLD,
    DEFAULT_WATER_INTERVAL_DAYS,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    SEEDLING_DEFAULT_THRESHOLD,
)
from .coordinator import AdaptiveIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_type = entry.data.get("entry_type")
    domain_data = hass.data.get(DOMAIN, {})

    if entry_type == ENTRY_TYPE_SYSTEM:
        async_add_entities([DailyBudgetNumber(hass, entry)])
        return

    coordinator: AdaptiveIrrigationCoordinator = domain_data[entry.entry_id]
    entities: list[NumberEntity] = [
        SoilThresholdNumber(coordinator),
        SeedlingThresholdNumber(coordinator),
        WaterIntervalNumber(coordinator),
        MaxDurationNumber(coordinator),
        FlowRateNumber(coordinator),
        SoakCyclesNumber(coordinator),
        SoakPauseMinutesNumber(coordinator),
        RefillPointNumber(coordinator),
        FillTargetNumber(coordinator),
        FallbackDurationNumber(coordinator),
    ]
    # Cooling controls only make sense on zones with a root-zone probe.
    if coordinator.config.get(CONF_SOIL_TEMP_SENSOR):
        entities.extend([
            CoolingThresholdNumber(coordinator),
            CoolingDurationNumber(coordinator),
        ])
    # Legacy: no system entry yet — add DailyBudgetNumber so existing installs don't lose it
    if "system_entry_id" not in domain_data and not domain_data.get("system_number_added"):
        domain_data["system_number_added"] = True
        entities.append(DailyBudgetNumber(hass, None))
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
        super().__init__(coordinator, "soil_threshold", "Soil Threshold", "%", 10.0, 99.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_threshold(self._current_value)


class SeedlingThresholdNumber(_ZoneNumber):
    _attr_icon = "mdi:sprout"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        super().__init__(coordinator, "seedling_threshold", "Seedling Threshold", "%", 10.0, 99.0, 1.0, SEEDLING_DEFAULT_THRESHOLD)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_seedling_threshold(self._current_value)


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


class SoakCyclesNumber(_ZoneNumber):
    _attr_icon = "mdi:repeat"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_SOAK_CYCLES, DEFAULT_SOAK_CYCLES)
        super().__init__(coordinator, "soak_cycles", "Soak Cycles", "cycles", 1.0, 5.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_soak_cycles(int(self._current_value))


class SoakPauseMinutesNumber(_ZoneNumber):
    _attr_icon = "mdi:timer-pause-outline"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_SOAK_PAUSE_MINUTES, DEFAULT_SOAK_PAUSE_MINUTES)
        super().__init__(coordinator, "soak_pause_minutes", "Soak Pause", "min", 5.0, 120.0, 5.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_soak_pause_minutes(int(self._current_value))


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

    def __init__(self, hass, entry=None) -> None:
        default = DEFAULT_DAILY_BUDGET_GALLONS
        if entry is not None:
            default = float(entry.options.get(CONF_DAILY_BUDGET_GALLONS,
                            entry.data.get(CONF_DAILY_BUDGET_GALLONS, DEFAULT_DAILY_BUDGET_GALLONS)))
        super().__init__(hass, default)

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


class RefillPointNumber(_ZoneNumber):
    """Moisture level at which the zone has earned its next deep soak.

    Under the interval-adaptive model this replaces Soil Threshold as the
    trigger. Lower means longer, deeper dry-down cycles; do not lower it on
    turf that is already heat-stressed.
    """

    _attr_icon = "mdi:water-alert-outline"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_REFILL_POINT, DEFAULT_REFILL_POINT)
        super().__init__(coordinator, "refill_point", "Refill Point", "%", 10.0, 90.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_refill_point(self._current_value)


class FillTargetNumber(_ZoneNumber):
    """Moisture level a soak aims for — roughly this probe's field capacity."""

    _attr_icon = "mdi:water-plus-outline"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_FILL_TARGET, DEFAULT_FILL_TARGET)
        super().__init__(coordinator, "fill_target", "Fill Target", "%", 20.0, 99.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_fill_target(self._current_value)


class FallbackDurationNumber(_ZoneNumber):
    """Soak length used when no calibration estimate is available.

    Previously config-only, which meant a bad calibration could not be worked
    around from the dashboard.
    """

    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_FALLBACK_DURATION, DEFAULT_FALLBACK_DURATION)
        super().__init__(coordinator, "fallback_duration", "Fallback Duration", "min", 1.0, 90.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_fallback_duration(int(self._current_value))


class CoolingThresholdNumber(_ZoneNumber):
    """Root-zone temperature at which cooling arms for this zone."""

    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_COOLING_TEMP_THRESHOLD, DEFAULT_COOLING_TEMP_THRESHOLD)
        super().__init__(coordinator, "cooling_threshold", "Cooling Threshold", "°F", 80.0, 120.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_cooling_threshold(self._current_value)


class CoolingDurationNumber(_ZoneNumber):
    """Length of a cooling application. Syringing is 2-3 min, not a soak."""

    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        default = coordinator.config.get(CONF_COOLING_DURATION, DEFAULT_COOLING_DURATION)
        super().__init__(coordinator, "cooling_duration", "Cooling Duration", "min", 1.0, 10.0, 1.0, default)

    def _push_to_coordinator(self) -> None:
        self.coordinator.set_live_cooling_duration(int(self._current_value))
