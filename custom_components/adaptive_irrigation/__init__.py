import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_BUDGET_GALLONS,
    CONF_WATER_METER_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_WINDOW_END_HOUR,
    DEFAULT_WINDOW_START_HOUR,
    DOMAIN,
)
from .coordinator import AdaptiveIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AdaptiveIrrigationCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = coordinator
    # Propagate shared weather entity so all coordinators read from one place
    weather = entry.data.get(CONF_WEATHER_ENTITY) or entry.options.get(CONF_WEATHER_ENTITY)
    if weather:
        domain_data["weather_entity"] = weather

    # Propagate global water budget settings from primary zone entry
    water_meter = entry.data.get(CONF_WATER_METER_ENTITY) or entry.options.get(CONF_WATER_METER_ENTITY)
    if water_meter:
        domain_data["water_meter_entity"] = water_meter
    budget = entry.data.get(CONF_DAILY_BUDGET_GALLONS) or entry.options.get(CONF_DAILY_BUDGET_GALLONS)
    if budget is not None:
        domain_data.setdefault("daily_budget_gallons", float(budget))
    domain_data.setdefault("daily_used_gallons", 0.0)
    domain_data.setdefault("budget_date", dt_util.now().date().isoformat())
    domain_data.setdefault("water_restriction", False)
    domain_data.setdefault("window_start_hour", DEFAULT_WINDOW_START_HOUR)
    domain_data.setdefault("window_end_hour", DEFAULT_WINDOW_END_HOUR)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "water_zone"):
        return  # already registered by a previous zone's setup

    async def handle_water_zone(call):
        zone_id = call.data["zone_id"]
        duration = int(call.data["duration_minutes"])
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, AdaptiveIrrigationCoordinator) and coord.zone_name == zone_id:
                await coord.water_now(duration)
                return
        _LOGGER.warning("water_zone: zone '%s' not found", zone_id)

    async def handle_evaluate_now(call):
        zone_id = call.data["zone_id"]
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, AdaptiveIrrigationCoordinator) and coord.zone_name == zone_id:
                await coord.async_refresh()
                return
        _LOGGER.warning("evaluate_now: zone '%s' not found", zone_id)

    hass.services.async_register(DOMAIN, "water_zone", handle_water_zone)
    hass.services.async_register(DOMAIN, "evaluate_now", handle_evaluate_now)
