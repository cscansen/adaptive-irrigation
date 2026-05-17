from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE, DOMAIN, ZONE_TYPE_SEEDLING
from .coordinator import AdaptiveIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AdaptiveIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        AdaptiveIrrigationZoneSwitch(coordinator),
        SeedlingModeSwitch(coordinator),
    ]
    if not hass.data[DOMAIN].get("master_switch_added"):
        hass.data[DOMAIN]["master_switch_added"] = True
        entities.append(AdaptiveIrrigationMasterSwitch())
        entities.append(WaterRestrictionSwitch())
    async_add_entities(entities)


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
            self.coordinator.set_auto_enabled(self._is_on)

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
        self.coordinator.set_auto_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.coordinator.set_auto_enabled(False)
        self.async_write_ha_state()


class SeedlingModeSwitch(
    CoordinatorEntity[AdaptiveIrrigationCoordinator], RestoreEntity, SwitchEntity
):
    _attr_icon = "mdi:seed-outline"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        super().__init__(coordinator)
        zone = coordinator.zone_name
        self._attr_unique_id = f"{DOMAIN}_{zone}_seedling_mode"
        self._attr_has_entity_name = True
        self._attr_name = "Seedling Mode"
        self._is_on = coordinator.config.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE) == ZONE_TYPE_SEEDLING

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == "on"
        self.coordinator.set_seedling_mode(self._is_on)

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
        self.coordinator.set_seedling_mode(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.coordinator.set_seedling_mode(False)
        self.async_write_ha_state()


class AdaptiveIrrigationMasterSwitch(RestoreEntity, SwitchEntity):
    """Integration-level pause switch — blocks all zones when off."""

    _attr_icon = "mdi:water-pump"
    _attr_unique_id = "adaptive_irrigation_master"
    _attr_name = "System Active"
    _attr_has_entity_name = False

    def __init__(self) -> None:
        self._is_on = True

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "configuration")},
            "name": "Configuration",
            "manufacturer": "adaptive_irrigation",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == "on"
        self.hass.data[DOMAIN]["master_enabled"] = self._is_on

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        self._is_on = True
        self.hass.data[DOMAIN]["master_enabled"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.hass.data[DOMAIN]["master_enabled"] = False
        self.async_write_ha_state()


class WaterRestrictionSwitch(RestoreEntity, SwitchEntity):
    """Global water restriction — when on, all zones are blocked from watering."""

    _attr_icon = "mdi:water-off"
    _attr_unique_id = "adaptive_irrigation_water_restriction"
    _attr_name = "Water Restriction"
    _attr_has_entity_name = False

    def __init__(self) -> None:
        self._is_on = False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "configuration")},
            "name": "Configuration",
            "manufacturer": "adaptive_irrigation",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == "on"
        self.hass.data[DOMAIN]["water_restriction"] = self._is_on

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        self._is_on = True
        self.hass.data[DOMAIN]["water_restriction"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.hass.data[DOMAIN]["water_restriction"] = False
        self.async_write_ha_state()
