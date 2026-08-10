from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_CROP_COEFFICIENT,
    CONF_DAILY_BUDGET_GALLONS,
    CONF_FALLBACK_DURATION,
    CONF_MAX_DURATION,
    CONF_MIN_INTERVAL,
    CONF_MOTION_SENSOR,
    CONF_SENSOR_REQUIRED,
    CONF_SOIL_SENSORS,
    CONF_SOIL_THRESHOLD,
    CONF_VALVE_SWITCH,
    CONF_WATER_INTERVAL_DAYS,
    CONF_WATER_METER_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_WINDOW_END_HOUR,
    CONF_WINDOW_START_HOUR,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DEFAULT_CROP_COEFFICIENT,
    DEFAULT_DAILY_BUDGET_GALLONS,
    DEFAULT_FALLBACK_DURATION,
    DEFAULT_MAX_DURATION,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_SOIL_THRESHOLD,
    DEFAULT_WATER_INTERVAL_DAYS,
    DEFAULT_WEATHER_ENTITY,
    DEFAULT_WINDOW_END_HOUR,
    DEFAULT_WINDOW_START_HOUR,
    DEFAULT_ZONE_TYPE,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    ENTRY_TYPE_ZONE,
    HOUR_LABELS,
    CONF_COOLING_DURATION,
    CONF_COOLING_ENABLED,
    CONF_COOLING_MAX_RUNS_PER_DAY,
    CONF_COOLING_MIN_INTERVAL,
    CONF_COOLING_MOISTURE_CEILING,
    CONF_COOLING_TEMP_THRESHOLD,
    CONF_COOLING_WIND_LIMIT,
    CONF_COOLING_WINDOW_END_HOUR,
    CONF_COOLING_WINDOW_START_HOUR,
    CONF_FILL_TARGET,
    CONF_REFILL_POINT,
    CONF_SOIL_TEMP_SENSOR,
    DEFAULT_COOLING_DURATION,
    DEFAULT_COOLING_ENABLED,
    DEFAULT_COOLING_MAX_RUNS_PER_DAY,
    DEFAULT_COOLING_MIN_INTERVAL,
    DEFAULT_COOLING_MOISTURE_CEILING,
    DEFAULT_COOLING_TEMP_THRESHOLD,
    DEFAULT_COOLING_WIND_LIMIT,
    DEFAULT_COOLING_WINDOW_END_HOUR,
    DEFAULT_COOLING_WINDOW_START_HOUR,
    DEFAULT_FILL_TARGET,
    DEFAULT_REFILL_POINT,
    SEEDLING_DEFAULT_FALLBACK,
    SEEDLING_DEFAULT_THRESHOLD,
    ZONE_TYPE_SEEDLING,
    ZONE_TYPE_SUMMER,
)

ZONE_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=ZONE_TYPE_SUMMER, label="Summer (daily threshold-based)"),
    selector.SelectOptionDict(value=ZONE_TYPE_SEEDLING, label="Seedling / Germination (4×/day windows, 93% threshold)"),
]

CROP_OPTIONS = [
    selector.SelectOptionDict(value="0.8", label="Lawn (Kc 0.8)"),
    selector.SelectOptionDict(value="0.9", label="Mixed lawn + shrubs (Kc 0.9)"),
    selector.SelectOptionDict(value="1.0", label="Garden / vegetables (Kc 1.0)"),
    selector.SelectOptionDict(value="0.6", label="Drip / trees (Kc 0.6)"),
]

HOUR_OPTIONS = [selector.SelectOptionDict(value=HOUR_LABELS[i], label=HOUR_LABELS[i]) for i in range(24)]


def _system_schema_dict(defaults: dict) -> dict:
    start_default = HOUR_LABELS[int(defaults.get(CONF_WINDOW_START_HOUR, DEFAULT_WINDOW_START_HOUR))]
    end_default   = HOUR_LABELS[int(defaults.get(CONF_WINDOW_END_HOUR,   DEFAULT_WINDOW_END_HOUR))]
    cool_start_default = HOUR_LABELS[int(defaults.get(CONF_COOLING_WINDOW_START_HOUR, DEFAULT_COOLING_WINDOW_START_HOUR))]
    cool_end_default   = HOUR_LABELS[int(defaults.get(CONF_COOLING_WINDOW_END_HOUR,   DEFAULT_COOLING_WINDOW_END_HOUR))]
    return {
        vol.Required(CONF_WEATHER_ENTITY, default=defaults.get(CONF_WEATHER_ENTITY, DEFAULT_WEATHER_ENTITY)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="weather")
        ),
        vol.Required(CONF_WINDOW_START_HOUR, default=start_default): selector.SelectSelector(
            selector.SelectSelectorConfig(options=HOUR_OPTIONS)
        ),
        vol.Required(CONF_WINDOW_END_HOUR, default=end_default): selector.SelectSelector(
            selector.SelectSelectorConfig(options=HOUR_OPTIONS)
        ),
        vol.Optional(CONF_WATER_METER_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_DAILY_BUDGET_GALLONS, default=float(defaults.get(CONF_DAILY_BUDGET_GALLONS, DEFAULT_DAILY_BUDGET_GALLONS))): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=5000, step=10, unit_of_measurement="gal")
        ),
        # --- Heat-stress cooling (system-wide limits) ---
        vol.Optional(CONF_COOLING_WINDOW_START_HOUR, default=cool_start_default): selector.SelectSelector(
            selector.SelectSelectorConfig(options=HOUR_OPTIONS)
        ),
        vol.Optional(CONF_COOLING_WINDOW_END_HOUR, default=cool_end_default): selector.SelectSelector(
            selector.SelectSelectorConfig(options=HOUR_OPTIONS)
        ),
        vol.Optional(CONF_COOLING_MAX_RUNS_PER_DAY, default=defaults.get(CONF_COOLING_MAX_RUNS_PER_DAY, DEFAULT_COOLING_MAX_RUNS_PER_DAY)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=10, step=1)
        ),
        vol.Optional(CONF_COOLING_MIN_INTERVAL, default=defaults.get(CONF_COOLING_MIN_INTERVAL, DEFAULT_COOLING_MIN_INTERVAL)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=15, max=240, step=15, unit_of_measurement="min")
        ),
        vol.Optional(CONF_COOLING_WIND_LIMIT, default=defaults.get(CONF_COOLING_WIND_LIMIT, DEFAULT_COOLING_WIND_LIMIT)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=5, max=40, step=1, unit_of_measurement="mph")
        ),
    }


def _zone_schema_dict(defaults: dict) -> dict:
    zone_type = defaults.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
    is_seedling = zone_type == ZONE_TYPE_SEEDLING
    default_threshold = defaults.get(CONF_SOIL_THRESHOLD, SEEDLING_DEFAULT_THRESHOLD if is_seedling else DEFAULT_SOIL_THRESHOLD)
    default_fallback = defaults.get(CONF_FALLBACK_DURATION, SEEDLING_DEFAULT_FALLBACK if is_seedling else DEFAULT_FALLBACK_DURATION)

    return {
        vol.Required(CONF_ZONE_NAME, default=defaults.get(CONF_ZONE_NAME, "")): str,
        vol.Required(CONF_ZONE_TYPE, default=zone_type): selector.SelectSelector(
            selector.SelectSelectorConfig(options=ZONE_TYPE_OPTIONS)
        ),
        vol.Required(CONF_VALVE_SWITCH, default=defaults.get(CONF_VALVE_SWITCH, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Optional(CONF_SOIL_SENSORS, default=defaults.get(CONF_SOIL_SENSORS, [])): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", multiple=True)
        ),
        vol.Optional(CONF_MOTION_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        ),
        vol.Optional(CONF_SOIL_THRESHOLD, default=default_threshold): selector.NumberSelector(
            selector.NumberSelectorConfig(min=50, max=99, step=1, unit_of_measurement="%")
        ),
        vol.Optional(CONF_MAX_DURATION, default=defaults.get(CONF_MAX_DURATION, DEFAULT_MAX_DURATION)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="min")
        ),
        vol.Optional(CONF_FALLBACK_DURATION, default=default_fallback): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=30, step=1, unit_of_measurement="min")
        ),
        vol.Optional(CONF_CROP_COEFFICIENT, default=defaults.get(CONF_CROP_COEFFICIENT, DEFAULT_CROP_COEFFICIENT)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=CROP_OPTIONS)
        ),
        vol.Optional(CONF_SENSOR_REQUIRED, default=defaults.get(CONF_SENSOR_REQUIRED, True)): selector.BooleanSelector(),
        vol.Optional(CONF_WATER_INTERVAL_DAYS, default=defaults.get(CONF_WATER_INTERVAL_DAYS, DEFAULT_WATER_INTERVAL_DAYS)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=14, step=1, unit_of_measurement="days")
        ),
        vol.Optional(CONF_MIN_INTERVAL, default=defaults.get(CONF_MIN_INTERVAL, DEFAULT_MIN_INTERVAL)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=15, max=240, step=15, unit_of_measurement="min")
        ),
        # --- Interval-adaptive model ---
        vol.Optional(CONF_REFILL_POINT, default=defaults.get(CONF_REFILL_POINT, DEFAULT_REFILL_POINT)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=90, step=1, unit_of_measurement="%")
        ),
        vol.Optional(CONF_FILL_TARGET, default=defaults.get(CONF_FILL_TARGET, DEFAULT_FILL_TARGET)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=20, max=99, step=1, unit_of_measurement="%")
        ),
        # --- Heat-stress cooling (per zone) ---
        vol.Optional(CONF_SOIL_TEMP_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Optional(CONF_COOLING_ENABLED, default=defaults.get(CONF_COOLING_ENABLED, DEFAULT_COOLING_ENABLED)): selector.BooleanSelector(),
        vol.Optional(CONF_COOLING_TEMP_THRESHOLD, default=defaults.get(CONF_COOLING_TEMP_THRESHOLD, DEFAULT_COOLING_TEMP_THRESHOLD)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=80, max=120, step=1, unit_of_measurement="°F")
        ),
        vol.Optional(CONF_COOLING_DURATION, default=defaults.get(CONF_COOLING_DURATION, DEFAULT_COOLING_DURATION)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=10, step=1, unit_of_measurement="min")
        ),
        vol.Optional(CONF_COOLING_MOISTURE_CEILING, default=defaults.get(CONF_COOLING_MOISTURE_CEILING, DEFAULT_COOLING_MOISTURE_CEILING)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=40, max=99, step=1, unit_of_measurement="%")
        ),
    }


def _zone_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(_zone_schema_dict(defaults))


def _coerce_system_input(user_input: dict) -> dict:
    """Convert window hour labels back to integers before storing."""
    data = dict(user_input)
    if CONF_WINDOW_START_HOUR in data:
        val = data[CONF_WINDOW_START_HOUR]
        data[CONF_WINDOW_START_HOUR] = HOUR_LABELS.index(val) if val in HOUR_LABELS else int(val)
    if CONF_WINDOW_END_HOUR in data:
        val = data[CONF_WINDOW_END_HOUR]
        data[CONF_WINDOW_END_HOUR] = HOUR_LABELS.index(val) if val in HOUR_LABELS else int(val)
    for key in (CONF_COOLING_WINDOW_START_HOUR, CONF_COOLING_WINDOW_END_HOUR):
        if key in data:
            val = data[key]
            data[key] = HOUR_LABELS.index(val) if val in HOUR_LABELS else int(val)
    return data


class AdaptiveIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        existing = self.hass.config_entries.async_entries(DOMAIN)
        has_system = any(e.data.get("entry_type") == ENTRY_TYPE_SYSTEM for e in existing)
        if has_system:
            return await self.async_step_zone()
        return await self.async_step_system()

    async def async_step_system(self, user_input=None):
        errors: dict = {}
        if user_input is not None:
            weather = user_input[CONF_WEATHER_ENTITY]
            if not self.hass.states.get(weather):
                errors[CONF_WEATHER_ENTITY] = "weather_entity_not_found"
            else:
                coerced = _coerce_system_input(user_input)
                return self.async_create_entry(
                    title="Configuration",
                    data={"entry_type": ENTRY_TYPE_SYSTEM, **coerced},
                )

        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema(_system_schema_dict({})),
            errors=errors,
        )

    async def async_step_zone(self, user_input=None):
        errors: dict = {}
        if user_input is not None:
            zone = user_input[CONF_ZONE_NAME].strip()
            if not zone:
                errors[CONF_ZONE_NAME] = "zone_name_required"
            else:
                await self.async_set_unique_id(f"{DOMAIN}_zone_{zone}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=zone,
                    data={"entry_type": ENTRY_TYPE_ZONE, **user_input},
                )

        return self.async_show_form(
            step_id="zone",
            data_schema=_zone_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        if config_entry.data.get("entry_type") == ENTRY_TYPE_SYSTEM:
            return SystemOptionsFlow(config_entry)
        return ZoneOptionsFlow(config_entry)


class SystemOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        defaults = {**self._entry.data, **self._entry.options}
        errors: dict = {}

        if user_input is not None:
            weather = user_input.get(CONF_WEATHER_ENTITY, defaults.get(CONF_WEATHER_ENTITY, DEFAULT_WEATHER_ENTITY))
            if not self.hass.states.get(weather):
                errors[CONF_WEATHER_ENTITY] = "weather_entity_not_found"
            else:
                coerced = _coerce_system_input(user_input)
                domain_data = self.hass.data.setdefault(DOMAIN, {})
                domain_data["weather_entity"] = coerced[CONF_WEATHER_ENTITY]
                domain_data["window_start_hour"] = coerced[CONF_WINDOW_START_HOUR]
                domain_data["window_end_hour"]   = coerced[CONF_WINDOW_END_HOUR]
                meter = coerced.get(CONF_WATER_METER_ENTITY, "")
                if meter:
                    domain_data["water_meter_entity"] = meter
                budget = coerced.get(CONF_DAILY_BUDGET_GALLONS)
                if budget is not None:
                    domain_data["daily_budget_gallons"] = float(budget)
                return self.async_create_entry(title="", data=coerced)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_system_schema_dict(defaults)),
            errors=errors,
        )


class ZoneOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        defaults = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_zone_schema(defaults),
        )
