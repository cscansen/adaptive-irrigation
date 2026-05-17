from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_CROP_COEFFICIENT,
    CONF_FALLBACK_DURATION,
    CONF_MAX_DURATION,
    CONF_MIN_INTERVAL,
    CONF_MOTION_SENSOR,
    CONF_SENSOR_REQUIRED,
    CONF_SOIL_SENSORS,
    CONF_SOIL_THRESHOLD,
    CONF_VALVE_SWITCH,
    CONF_WATER_INTERVAL_DAYS,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DEFAULT_CROP_COEFFICIENT,
    DEFAULT_FALLBACK_DURATION,
    DEFAULT_MAX_DURATION,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_SOIL_THRESHOLD,
    DEFAULT_WATER_INTERVAL_DAYS,
    DEFAULT_WEATHER_ENTITY,
    DEFAULT_ZONE_TYPE,
    DOMAIN,
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


def _zone_schema_dict(defaults: dict) -> dict:
    zone_type = defaults.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
    is_seedling = zone_type == ZONE_TYPE_SEEDLING
    default_threshold = defaults.get(CONF_SOIL_THRESHOLD, SEEDLING_DEFAULT_THRESHOLD if is_seedling else DEFAULT_SOIL_THRESHOLD)
    default_fallback = defaults.get(CONF_FALLBACK_DURATION, SEEDLING_DEFAULT_FALLBACK if is_seedling else DEFAULT_FALLBACK_DURATION)

    d: dict = {
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
    }
    return d


def _zone_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(_zone_schema_dict(defaults))


class AdaptiveIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._weather_entity: str = DEFAULT_WEATHER_ENTITY

    async def async_step_user(self, user_input=None):
        existing = self.hass.config_entries.async_entries(DOMAIN)
        if existing:
            # Inherit weather entity from an existing zone entry
            for entry in existing:
                w = entry.data.get(CONF_WEATHER_ENTITY) or entry.options.get(CONF_WEATHER_ENTITY)
                if w:
                    self._weather_entity = w
                    break
            return await self.async_step_zone()
        # First zone ever — ask for weather source first
        return await self.async_step_system()

    async def async_step_system(self, user_input=None):
        errors: dict = {}
        if user_input is not None:
            weather = user_input[CONF_WEATHER_ENTITY]
            if not self.hass.states.get(weather):
                errors[CONF_WEATHER_ENTITY] = "weather_entity_not_found"
            else:
                self._weather_entity = weather
                return await self.async_step_zone()

        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema({
                vol.Required(CONF_WEATHER_ENTITY, default=self._weather_entity): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
            }),
            errors=errors,
        )

    async def async_step_zone(self, user_input=None):
        errors: dict = {}
        if user_input is not None:
            zone = user_input[CONF_ZONE_NAME].strip()
            if not zone:
                errors[CONF_ZONE_NAME] = "zone_name_required"
            else:
                await self.async_set_unique_id(f"{DOMAIN}_{zone}")
                self._abort_if_unique_id_configured()
                # Store weather entity only on entries that set it (i.e. the first zone)
                existing = self.hass.config_entries.async_entries(DOMAIN)
                data = dict(user_input)
                if not existing:
                    data[CONF_WEATHER_ENTITY] = self._weather_entity
                return self.async_create_entry(title=zone, data=data)

        return self.async_show_form(
            step_id="zone",
            data_schema=_zone_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return AdaptiveIrrigationOptionsFlow(config_entry)


class AdaptiveIrrigationOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        is_primary = CONF_WEATHER_ENTITY in self._entry.data or CONF_WEATHER_ENTITY in self._entry.options
        defaults = {**self._entry.data, **self._entry.options}
        errors: dict = {}

        if user_input is not None:
            if is_primary:
                weather = user_input.get(CONF_WEATHER_ENTITY, defaults.get(CONF_WEATHER_ENTITY, DEFAULT_WEATHER_ENTITY))
                if not self.hass.states.get(weather):
                    errors[CONF_WEATHER_ENTITY] = "weather_entity_not_found"
                else:
                    self.hass.data.setdefault(DOMAIN, {})["weather_entity"] = weather
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        if is_primary:
            schema = vol.Schema({
                vol.Required(CONF_WEATHER_ENTITY, default=defaults.get(CONF_WEATHER_ENTITY, DEFAULT_WEATHER_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
                **_zone_schema_dict(defaults),
            })
        else:
            schema = _zone_schema(defaults)

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
