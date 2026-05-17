from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.dt import parse_datetime

from .const import DOMAIN, ENTRY_TYPE_SYSTEM
from .coordinator import AdaptiveIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get("entry_type") == ENTRY_TYPE_SYSTEM:
        return
    coordinator: AdaptiveIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SeedlingExpiresDatetime(coordinator, coordinator.zone_name)])


class SeedlingExpiresDatetime(CoordinatorEntity[AdaptiveIrrigationCoordinator], RestoreEntity, DateTimeEntity):
    _attr_icon = "mdi:calendar-remove"
    _attr_has_entity_name = True

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator, zone: str) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"{DOMAIN}_{zone}_seedling_expires"
        self._attr_name = "Seedling Expires"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._zone)},
            "name": f"Adaptive Irrigation — {self._zone.replace('_', ' ').title()}",
            "manufacturer": "adaptive_irrigation",
        }

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.get("seedling_expires") if self.coordinator.data else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable"):
            dt = parse_datetime(last.state)
            if dt:
                self.coordinator.set_seedling_expires(dt)

    async def async_set_value(self, value: datetime) -> None:
        self.coordinator.set_seedling_expires(value)
        self.async_write_ha_state()
