import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SOIL_SENSORS,
    DOMAIN,
    SCAN_INTERVAL_MINUTES,
    STALE_SENSOR_HOURS,
    TREND_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class AdaptiveIrrigationCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data['zone_name']}",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )
        self.entry = entry
        self.zone_name = entry.data["zone_name"]
        self.config = entry.data

    async def _async_update_data(self) -> dict:
        moisture = self._read_soil_moisture()
        trend = await self._read_moisture_trend()
        return {
            "moisture": moisture,
            "trend": trend,
        }

    def _read_soil_moisture(self) -> float | None:
        sensors = self.config.get(CONF_SOIL_SENSORS, [])
        if not sensors:
            return None
        readings = []
        now = dt_util.utcnow()
        stale_cutoff = now - timedelta(hours=STALE_SENSOR_HOURS)
        for entity_id in sensors:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                continue
            if state.last_updated < stale_cutoff:
                _LOGGER.warning("%s: sensor %s stale (last updated %s)", self.zone_name, entity_id, state.last_updated)
                continue
            try:
                readings.append(float(state.state))
            except ValueError:
                pass
        return round(sum(readings) / len(readings), 1) if readings else None

    async def _read_moisture_trend(self) -> float | None:
        sensors = self.config.get(CONF_SOIL_SENSORS, [])
        if not sensors:
            return None

        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states

        entity_id = sensors[0]
        start = dt_util.utcnow() - timedelta(hours=TREND_HOURS)

        try:
            states = await get_instance(self.hass).async_add_executor_job(
                get_significant_states, self.hass, start, None, [entity_id]
            )
        except Exception as err:
            _LOGGER.warning("%s: recorder history unavailable, trend skipped: %s", self.zone_name, err)
            return None

        readings = []
        for s in states.get(entity_id, []):
            if s.state in ("unknown", "unavailable"):
                continue
            try:
                readings.append((s.last_updated.timestamp(), float(s.state)))
            except ValueError:
                pass

        if len(readings) < 3:
            return None

        xs, ys = zip(*readings)
        n = len(xs)
        denom = n * sum(x**2 for x in xs) - sum(xs) ** 2
        if denom == 0:
            return None
        slope = (n * sum(x * y for x, y in zip(xs, ys)) - sum(xs) * sum(ys)) / denom
        return round(slope * 3600, 3)  # per-second → %/hour
