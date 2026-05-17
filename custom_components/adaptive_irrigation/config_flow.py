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
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DEFAULT_CROP_COEFFICIENT,
    DEFAULT_FALLBACK_DURATION,
    DEFAULT_MAX_DURATION,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_SOIL_THRESHOLD,
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


def _zone_schema(defaults: dict) -> vol.Schema:
    zone_type = defaults.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
    is_seedling = zone_type == ZONE_TYPE_SEEDLING
    default_threshold = defaults.get(CONF_SOIL_THRESHOLD, SEEDLING_DEFAULT_THRESHOLD if is_seedling else DEFAULT_SOIL_THRESHOLD)
    default_fallback = defaults.get(CONF_FALLBACK_DURATION, SEEDLING_DEFAULT_FALLBACK if is_seedling else DEFAULT_FALLBACK_DURATION)

    return vol.Schema(
        {
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
            vol.Optional(CONF_MOTION_SENSOR, default=defaults.get(CONF_MOTION_SENSOR, "")): selector.EntitySelector(
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
            vol.Optional(CONF_MIN_INTERVAL, default=defaults.get(CONF_MIN_INTERVAL, DEFAULT_MIN_INTERVAL)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=15, max=240, step=15, unit_of_measurement="min")
            ),
        }
    )


class AdaptiveIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            zone = user_input[CONF_ZONE_NAME].strip()
            if not zone:
                errors[CONF_ZONE_NAME] = "zone_name_required"
            else:
                await self.async_set_unique_id(f"{DOMAIN}_{zone}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=zone, data=user_input)

        return self.async_show_form(
            step_id="user",
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
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_zone_schema(dict(self._entry.data)),
        )
