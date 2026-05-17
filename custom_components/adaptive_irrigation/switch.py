from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdaptiveIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AdaptiveIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AdaptiveIrrigationZoneSwitch(coordinator)])


class AdaptiveIrrigationZoneSwitch(
    CoordinatorEntity[AdaptiveIrrigationCoordinator], RestoreEntity, SwitchEntity
):
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        super().__init__(coordinator)
        zone = coordinator.zone_name
        self._attr_unique_id = f"{DOMAIN}_{zone}_switch"
        self._attr_has_entity_name = True
        self._attr_name = "Auto Watering"
        self._is_on = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == "on"

    @property
    def device_info(self):
        zone = self.coordinator.zone_name
        return {
            "identifiers": {(DOMAIN, zone)},
            "name": f"Adaptive Irrigation — {zone.replace('_', ' ').title()}",
            "manufacturer": "adaptive_irrigation",
        }

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.async_write_ha_state()
