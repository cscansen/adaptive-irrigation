import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AdaptiveIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AdaptiveIrrigationCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
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
