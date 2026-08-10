import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COOLING_MAX_RUNS_PER_DAY,
    CONF_COOLING_MIN_INTERVAL,
    CONF_COOLING_WIND_LIMIT,
    CONF_COOLING_WINDOW_END_HOUR,
    CONF_COOLING_WINDOW_START_HOUR,
    DEFAULT_COOLING_MAX_RUNS_PER_DAY,
    DEFAULT_COOLING_MIN_INTERVAL,
    DEFAULT_COOLING_WIND_LIMIT,
    DEFAULT_COOLING_WINDOW_END_HOUR,
    DEFAULT_COOLING_WINDOW_START_HOUR,
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
PLATFORMS_ZONE   = [Platform.DATETIME, Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


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

    # Heat-stress cooling — system-wide limits. The end hour is additionally
    # clamped to COOLING_HARD_STOP_HOUR in the coordinator: a canopy left wet
    # overnight invites fungal disease, so that bound is not configurable.
    domain_data["cooling_enabled"] = True
    domain_data["cooling_window_start_hour"] = int(
        opts.get(CONF_COOLING_WINDOW_START_HOUR, DEFAULT_COOLING_WINDOW_START_HOUR))
    domain_data["cooling_window_end_hour"] = int(
        opts.get(CONF_COOLING_WINDOW_END_HOUR, DEFAULT_COOLING_WINDOW_END_HOUR))
    domain_data["cooling_max_runs_per_day"] = int(
        opts.get(CONF_COOLING_MAX_RUNS_PER_DAY, DEFAULT_COOLING_MAX_RUNS_PER_DAY))
    domain_data["cooling_min_interval"] = float(
        opts.get(CONF_COOLING_MIN_INTERVAL, DEFAULT_COOLING_MIN_INTERVAL))
    domain_data["cooling_wind_limit"] = float(
        opts.get(CONF_COOLING_WIND_LIMIT, DEFAULT_COOLING_WIND_LIMIT))

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
    await coordinator.async_load_from_store()
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
    def _find_coordinator(zone_id: str):
        needle = zone_id.lower().replace(" ", "_")
        for coord in hass.data.get(DOMAIN, {}).values():
            if hasattr(coord, "zone_name") and hasattr(coord, "async_refresh"):
                if coord.zone_name.lower().replace(" ", "_") == needle:
                    return coord
        return None

    async def handle_water_zone(call):
        zone_id = call.data["zone_id"]
        duration = int(call.data["duration_minutes"])
        coord = _find_coordinator(zone_id)
        if coord:
            await coord.water_now(duration)
        else:
            _LOGGER.warning("water_zone: zone '%s' not found", zone_id)

    async def handle_cool_zone(call):
        zone_id = call.data["zone_id"]
        duration = call.data.get("duration_minutes")
        coord = _find_coordinator(zone_id)
        if coord:
            await coord.cool_now(int(duration) if duration else None)
        else:
            _LOGGER.warning("cool_zone: zone '%s' not found", zone_id)

    async def handle_evaluate_now(call):
        zone_id = call.data["zone_id"]
        coord = _find_coordinator(zone_id)
        if coord:
            await coord.async_refresh()
        else:
            _LOGGER.warning("evaluate_now: zone '%s' not found", zone_id)

    async def handle_force_calibration(call):
        """Manually trigger the calibration followup for a zone right now.

        Useful after a manual watering run to immediately see whether the sensor
        detected a moisture rise and what rate was computed.
        """
        zone_id = call.data["zone_id"]
        coord = _find_coordinator(zone_id)
        if not coord:
            _LOGGER.warning("force_calibration: zone '%s' not found", zone_id)
            return
        coord.force_calibration_followup()

    async def handle_calibration_status(call):
        """Post a persistent notification with calibration debug info for all zones."""
        lines = ["## Adaptive Irrigation — Calibration Status\n"]
        for coord in hass.data.get(DOMAIN, {}).values():
            if not hasattr(coord, "zone_name") or not hasattr(coord, "_calibration"):
                continue
            moisture = coord._read_soil_moisture()
            cal = coord._calibration
            soil_before = coord._soil_before
            last_dur = coord._last_duration
            last_w = coord._last_watered
            from_store = coord._calibration_from_store

            rise_preview = None
            if moisture is not None and soil_before is not None:
                rise_preview = round(moisture - soil_before, 1)

            lines.append(f"### {coord.zone_name.replace('_', ' ').title()}")
            lines.append(f"- Calibration rate: **{f'{cal:.4f} %/min' if cal is not None else 'unknown'}**")
            lines.append(f"- Source: {'Store ✓' if from_store else 'RestoreEntity / not yet computed'}")
            lines.append(f"- Current soil: {f'{moisture:.1f}%' if moisture is not None else 'unavailable'}")
            lines.append(f"- Soil before last water: {f'{soil_before:.1f}%' if soil_before is not None else 'not set (restart cleared it)'}")
            lines.append(f"- Last watering duration: {last_dur} min")
            lines.append(f"- Last watered: {last_w.isoformat() if last_w else 'unknown'}")
            if rise_preview is not None:
                lines.append(f"- Rise if followup ran now: {rise_preview:+.1f}%")
                if last_dur > 0 and rise_preview > 0:
                    projected_rate = round(rise_preview / last_dur, 4)
                    lines.append(f"- Projected rate if followup ran now: {projected_rate:.4f} %/min")
            lines.append("")

        await hass.services.async_call(
            "persistent_notification", "create",
            {
                "notification_id": "adaptive_irrigation_calibration_status",
                "title": "Irrigation Calibration Status",
                "message": "\n".join(lines),
            },
        )

    hass.services.async_register(DOMAIN, "water_zone", handle_water_zone)
    hass.services.async_register(DOMAIN, "cool_zone", handle_cool_zone)
    hass.services.async_register(DOMAIN, "evaluate_now", handle_evaluate_now)
    hass.services.async_register(DOMAIN, "force_calibration", handle_force_calibration)
    hass.services.async_register(DOMAIN, "calibration_status", handle_calibration_status)
