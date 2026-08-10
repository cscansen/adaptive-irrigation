from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SOIL_TEMP_SENSOR,
    CONF_ZONE_TYPE,
    DEFAULT_ZONE_TYPE,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    ZONE_TYPE_SEEDLING,
)
from .coordinator import AdaptiveIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_type = entry.data.get("entry_type")
    domain_data = hass.data.get(DOMAIN, {})

    if entry_type == ENTRY_TYPE_SYSTEM:
        async_add_entities([AdaptiveIrrigationMasterSwitch(), WaterRestrictionSwitch()])
        return

    coordinator: AdaptiveIrrigationCoordinator = domain_data[entry.entry_id]
    entities: list[SwitchEntity] = [
        AdaptiveIrrigationZoneSwitch(coordinator),
        SeedlingModeSwitch(coordinator),
    ]
    if coordinator.config.get(CONF_SOIL_TEMP_SENSOR):
        entities.append(CoolingEnabledSwitch(coordinator))
    # Legacy backward-compat
    if "system_entry_id" not in domain_data and not domain_data.get("master_switch_added"):
        domain_data["master_switch_added"] = True
        entities.extend([AdaptiveIrrigationMasterSwitch(), WaterRestrictionSwitch()])
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


class CoolingEnabledSwitch(
    CoordinatorEntity[AdaptiveIrrigationCoordinator], RestoreEntity, SwitchEntity
):
    """Per-zone enable for heat-stress cooling.

    Deliberately separate from Auto Watering: cooling is a heat intervention,
    not irrigation, and it is reasonable to want one without the other. Both
    the master switch and the water-restriction switch still override this.
    """

    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: AdaptiveIrrigationCoordinator) -> None:
        super().__init__(coordinator)
        zone = coordinator.zone_name
        self._attr_unique_id = f"{DOMAIN}_{zone}_cooling_enabled"
        self._attr_has_entity_name = True
        self._attr_name = "Heat Cooling"
        self._is_on = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == "on"
        self.coordinator.set_cooling_enabled(self._is_on)

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
        self.coordinator.set_cooling_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.coordinator.set_cooling_enabled(False)
        self.async_write_ha_state()
