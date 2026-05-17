from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_WINDOW_END_HOUR,
    CONF_WINDOW_START_HOUR,
    DEFAULT_WINDOW_END_HOUR,
    DEFAULT_WINDOW_START_HOUR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    HOUR_LABELS,
)

_CONFIG_DEVICE = {
    "identifiers": {(DOMAIN, "configuration")},
    "name": "Configuration",
    "manufacturer": "adaptive_irrigation",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get("entry_type") != ENTRY_TYPE_SYSTEM:
        return
    async_add_entities([
        WindowStartHourSelect(hass, entry),
        WindowEndHourSelect(hass, entry),
    ])


class _WindowHourSelect(RestoreEntity, SelectEntity):
    _attr_has_entity_name = False
    _attr_options = HOUR_LABELS

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, conf_key: str, default: int) -> None:
        self._hass = hass
        hour = int(entry.options.get(conf_key, entry.data.get(conf_key, default)))
        self._current_option: str = HOUR_LABELS[hour]

    @property
    def device_info(self):
        return _CONFIG_DEVICE

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in HOUR_LABELS:
            self._current_option = last.state
        self._push_to_domain()

    def _push_to_domain(self) -> None:
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        self._current_option = option
        self._push_to_domain()
        self.async_write_ha_state()


class WindowStartHourSelect(_WindowHourSelect):
    _attr_unique_id = "adaptive_irrigation_window_start_hour"
    _attr_name = "Watering Window Start"
    _attr_icon = "mdi:clock-start"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, CONF_WINDOW_START_HOUR, DEFAULT_WINDOW_START_HOUR)

    def _push_to_domain(self) -> None:
        self._hass.data[DOMAIN]["window_start_hour"] = HOUR_LABELS.index(self._current_option)


class WindowEndHourSelect(_WindowHourSelect):
    _attr_unique_id = "adaptive_irrigation_window_end_hour"
    _attr_name = "Watering Window End"
    _attr_icon = "mdi:clock-end"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, CONF_WINDOW_END_HOUR, DEFAULT_WINDOW_END_HOUR)

    def _push_to_domain(self) -> None:
        self._hass.data[DOMAIN]["window_end_hour"] = HOUR_LABELS.index(self._current_option)
