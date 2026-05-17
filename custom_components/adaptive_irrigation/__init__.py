import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_BUDGET_GALLONS,
    CONF_WATER_METER_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_WINDOW_END_HOUR,
    CONF_WINDOW_START_HOUR,
    DEFAULT_WEATHER_ENTITY,
    DEFAULT_WINDOW_END_HOUR,
    DEFAULT_WINDOW_START_HOUR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    ENTRY_TYPE_ZONE,
)
from .coordinator import AdaptiveIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS_SYSTEM = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
PLATFORMS_ZONE   = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Migrating adaptive_irrigation entry '%s' from version %s", entry.title, entry.version)
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, "entry_type": ENTRY_TYPE_ZONE},
            version=2,
        )
        _LOGGER.info("Migrated entry '%s' to version 2 (entry_type=zone)", entry.title)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get("entry_type") == ENTRY_TYPE_SYSTEM:
        return await _setup_system_entry(hass, entry)
    return await _setup_zone_entry(hass, entry)


async def _setup_system_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data["system_entry_id"] = entry.entry_id

    opts = {**entry.data, **entry.options}
    domain_data["weather_entity"] = opts.get(CONF_WEATHER_ENTITY, DEFAULT_WEATHER_ENTITY)

    meter = opts.get(CONF_WATER_METER_ENTITY, "")
    if meter:
        domain_data["water_meter_entity"] = meter

    domain_data["daily_budget_gallons"] = float(opts.get(CONF_DAILY_BUDGET_GALLONS, 0.0))
    domain_data.setdefault("daily_used_gallons", 0.0)
    domain_data.setdefault("budget_date", dt_util.now().date().isoformat())
    domain_data.setdefault("water_restriction", False)
    domain_data["window_start_hour"] = int(opts.get(CONF_WINDOW_START_HOUR, DEFAULT_WINDOW_START_HOUR))
    domain_data["window_end_hour"]   = int(opts.get(CONF_WINDOW_END_HOUR,   DEFAULT_WINDOW_END_HOUR))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_SYSTEM)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _register_services(hass)
    return True


async def _setup_zone_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})

    # Legacy backward-compat: propagate system settings from old primary zone entry
    # until the user creates a dedicated system entry
    if "system_entry_id" not in domain_data:
        opts = {**entry.data, **entry.options}
        if CONF_WEATHER_ENTITY in opts:
            domain_data.setdefault("weather_entity", opts[CONF_WEATHER_ENTITY])
        meter = opts.get(CONF_WATER_METER_ENTITY, "")
        if meter:
            domain_data.setdefault("water_meter_entity", meter)
        if CONF_DAILY_BUDGET_GALLONS in opts:
            domain_data.setdefault("daily_budget_gallons", float(opts[CONF_DAILY_BUDGET_GALLONS]))
        domain_data.setdefault("daily_used_gallons", 0.0)
        domain_data.setdefault("budget_date", dt_util.now().date().isoformat())
        domain_data.setdefault("water_restriction", False)
        domain_data.setdefault("window_start_hour", DEFAULT_WINDOW_START_HOUR)
        domain_data.setdefault("window_end_hour", DEFAULT_WINDOW_END_HOUR)

    coordinator = AdaptiveIrrigationCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    domain_data[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_ZONE)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_type = entry.data.get("entry_type")
    platforms = PLATFORMS_SYSTEM if entry_type == ENTRY_TYPE_SYSTEM else PLATFORMS_ZONE
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        d = hass.data.get(DOMAIN, {})
        d.pop(entry.entry_id, None)
        if entry_type == ENTRY_TYPE_SYSTEM:
            d.pop("system_entry_id", None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "water_zone"):
        return

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
