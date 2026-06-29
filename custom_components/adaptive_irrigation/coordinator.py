from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CALIBRATION_FOLLOWUP_SECONDS,
    CONF_CROP_COEFFICIENT,
    CONF_FALLBACK_DURATION,
    CONF_MAX_DURATION,
    CONF_MIN_INTERVAL,
    CONF_MOTION_SENSOR,
    CONF_SENSOR_REQUIRED,
    CONF_SOAK_CYCLES,
    CONF_SOAK_PAUSE_MINUTES,
    CONF_SOIL_SENSORS,
    CONF_SOIL_THRESHOLD,
    CONF_VALVE_SWITCH,
    CONF_DAILY_BUDGET_GALLONS,
    CONF_FLOW_RATE_GPM,
    CONF_WATER_INTERVAL_DAYS,
    CONF_WEATHER_ENTITY,
    CONF_WINDOW_END_HOUR,
    CONF_WINDOW_START_HOUR,
    CONF_ZONE_TYPE,
    DEFAULT_CROP_COEFFICIENT,
    DEFAULT_DAILY_BUDGET_GALLONS,
    DEFAULT_FALLBACK_DURATION,
    DEFAULT_FLOW_RATE_GPM,
    DEFAULT_MAX_DURATION,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_SOAK_CYCLES,
    DEFAULT_SOAK_PAUSE_MINUTES,
    DEFAULT_SOIL_THRESHOLD,
    DEFAULT_WATER_INTERVAL_DAYS,
    DEFAULT_WEATHER_ENTITY,
    DEFAULT_WINDOW_END_HOUR,
    DEFAULT_WINDOW_START_HOUR,
    DEFAULT_ZONE_TYPE,
    DOMAIN,
    PEER_TREND_DRYING_THRESHOLD,
    SCAN_INTERVAL_MINUTES,
    SEEDLING_DEFAULT_THRESHOLD,
    STALE_SENSOR_HOURS,
    TREND_HOURS,
    ZONE_TYPE_SEEDLING,
)
from .logic import calibrated_duration, decide, hargreaves_et

_LOGGER = logging.getLogger(__name__)


class AdaptiveIrrigationCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data['zone_name']}",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
            config_entry=entry,
        )
        self.entry = entry
        self.zone_name = entry.data["zone_name"]
        # Merge options over data so OptionsFlow changes take effect on reload
        self.config = {**entry.data, **entry.options}

        self._auto_enabled: bool = True
        self._last_watered: datetime | None = None
        self._last_moisture: float | None = None
        self._calibration: float | None = None
        self._calibration_from_store: bool = False  # True once Store has loaded a value
        self._watering_lock = asyncio.Lock()
        self._soil_before: float | None = None
        self._last_duration: int = 0
        self._startup_poll_done: bool = False  # first poll skips watering; entities restore before second
        self._valve_seen_on: bool = False  # only True after we observe valve==on in this HA session

        self._store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_calibration")

        # Live-tunable values — None means fall back to config
        self._seedling_mode: bool | None = None
        self._seedling_expires: datetime | None = None
        self._live_threshold: float | None = None
        self._live_seedling_threshold: float | None = None
        self._live_water_interval_days: int | None = None
        self._live_max_duration: int | None = None
        self._live_flow_rate: float | None = None
        self._live_soak_cycles: int | None = None
        self._live_soak_pause_minutes: int | None = None

    # --- Effective-value properties (live entity overrides config) ---

    @property
    def _effective_seedling_mode(self) -> bool:
        if self._seedling_mode is not None:
            return self._seedling_mode
        return self.config.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE) == ZONE_TYPE_SEEDLING

    @property
    def _effective_threshold(self) -> float:
        if self._effective_seedling_mode:
            if self._live_seedling_threshold is not None:
                return self._live_seedling_threshold
            return float(SEEDLING_DEFAULT_THRESHOLD)
        if self._live_threshold is not None:
            return self._live_threshold
        return float(self.config.get(CONF_SOIL_THRESHOLD, DEFAULT_SOIL_THRESHOLD))

    @property
    def _effective_water_interval(self) -> int:
        if self._live_water_interval_days is not None:
            return self._live_water_interval_days
        return int(self.config.get(CONF_WATER_INTERVAL_DAYS, DEFAULT_WATER_INTERVAL_DAYS))

    @property
    def _effective_max_duration(self) -> int:
        if self._live_max_duration is not None:
            return self._live_max_duration
        return int(self.config.get(CONF_MAX_DURATION, DEFAULT_MAX_DURATION))

    @property
    def _effective_window_start_hour(self) -> int:
        return int(self.hass.data.get(DOMAIN, {}).get("window_start_hour", DEFAULT_WINDOW_START_HOUR))

    @property
    def _effective_window_end_hour(self) -> int:
        return int(self.hass.data.get(DOMAIN, {}).get("window_end_hour", DEFAULT_WINDOW_END_HOUR))

    @property
    def _effective_flow_rate(self) -> float:
        if self._live_flow_rate is not None:
            return self._live_flow_rate
        return float(self.config.get(CONF_FLOW_RATE_GPM, DEFAULT_FLOW_RATE_GPM))

    @property
    def _effective_soak_cycles(self) -> int:
        if self._live_soak_cycles is not None:
            return self._live_soak_cycles
        return int(self.config.get(CONF_SOAK_CYCLES, DEFAULT_SOAK_CYCLES))

    @property
    def _effective_soak_pause_minutes(self) -> int:
        if self._live_soak_pause_minutes is not None:
            return self._live_soak_pause_minutes
        return int(self.config.get(CONF_SOAK_PAUSE_MINUTES, DEFAULT_SOAK_PAUSE_MINUTES))

    # --- Entity callbacks (called after restore) ---

    def set_auto_enabled(self, enabled: bool) -> None:
        self._auto_enabled = enabled

    def set_last_watered(self, dt: datetime | None) -> None:
        self._last_watered = dt

    async def async_load_from_store(self) -> None:
        """Load persisted calibration from HA storage. Called before first_refresh."""
        stored = await self._store.async_load()
        if stored and stored.get("calibration") is not None:
            self._calibration = float(stored["calibration"])
            self._calibration_from_store = True
            _LOGGER.info(
                "%s: calibration loaded from store: %.4f %%/min",
                self.zone_name, self._calibration,
            )

    async def _persist_calibration(self) -> None:
        """Write current calibration to HA storage."""
        await self._store.async_save({"calibration": self._calibration})

    def set_calibration(self, rate: float | None) -> None:
        # Store takes priority — don't let RestoreEntity overwrite a store-loaded value.
        if self._calibration_from_store:
            return
        self._calibration = rate

    def set_seedling_mode(self, enabled: bool) -> None:
        self._seedling_mode = enabled

    def set_seedling_expires(self, dt: datetime | None) -> None:
        self._seedling_expires = dt

    def set_seedling_threshold(self, value: float) -> None:
        self._live_seedling_threshold = value

    def set_live_threshold(self, value: float) -> None:
        self._live_threshold = value

    def set_live_water_interval(self, value: int) -> None:
        self._live_water_interval_days = value

    def set_live_max_duration(self, value: int) -> None:
        self._live_max_duration = value

    def set_live_flow_rate(self, value: float) -> None:
        self._live_flow_rate = value

    def set_live_soak_cycles(self, value: int) -> None:
        self._live_soak_cycles = value

    def set_live_soak_pause_minutes(self, value: int) -> None:
        self._live_soak_pause_minutes = value

    # --- Main poll ---

    async def _async_update_data(self) -> dict:
        moisture = self._read_soil_moisture()
        trend = await self._read_moisture_trend()
        weather = await self._fetch_weather()
        et_today = self._compute_et(weather) if weather else None
        precip = round(float(weather.get("precipitation", 0) or 0), 2) if weather else 0.0
        wind = round(float(weather.get("wind_speed", 0) or 0), 1) if weather else 0.0

        # Auto-set seedling expiry (30 days) when seedling is on but no expiry is configured yet
        if self._effective_seedling_mode and self._seedling_expires is None:
            self._seedling_expires = dt_util.utcnow() + timedelta(days=30)


        # Auto-expire seedling mode
        if self._seedling_mode and self._seedling_expires is not None:
            if dt_util.utcnow() >= self._seedling_expires:
                self._seedling_mode = False
                zone_switch = f"switch.adaptive_irrigation_{self.zone_name}_seedling_mode"
                self.hass.async_create_task(
                    self.hass.services.async_call("switch", "turn_off", {"entity_id": zone_switch})
                )
                self._notify(
                    f"irrigation_{self.zone_name}_seedling_expired",
                    f"Seedling mode for {self.zone_name.replace('_', ' ').title()} expired and has been turned off.",
                )

        base = {
            "moisture": moisture,
            "trend": trend,
            "et_today": et_today,
            "precip": precip,
            "wind": wind,
            "last_watered": self._last_watered,
            "calibration": self._calibration,
            "seedling_expires": self._seedling_expires,
        }

        domain_data = self.hass.data.setdefault(DOMAIN, {})

        # Midnight budget reset
        today = dt_util.now().date().isoformat()
        if domain_data.get("budget_date") != today:
            domain_data["budget_date"] = today
            domain_data["daily_used_gallons"] = 0.0
            meter = domain_data.get("water_meter_entity")
            if meter:
                s = self.hass.states.get(meter)
                if s and s.state not in ("unknown", "unavailable"):
                    try:
                        domain_data["water_meter_baseline"] = float(s.state)
                    except ValueError:
                        pass

        if not self._auto_enabled:
            return {**base, "status": "Disabled"}

        if not domain_data.get("master_enabled", True):
            return {**base, "status": "Disabled — master switch off"}

        if domain_data.get("water_restriction", False):
            return {**base, "status": "Paused — water restriction active"}

        # Skip watering decisions on the very first poll — entities haven't restored
        # last_watered / calibration yet (restore happens after first_refresh completes).
        # If last_watered is still None after restore, seed it from valve switch history.
        if not self._startup_poll_done:
            self._startup_poll_done = True
            if self._last_watered is None:
                await self._init_last_watered_from_history()
            if moisture is None:
                moisture = await self._init_moisture_from_history()
                self._last_moisture = moisture
            return {**base, "moisture": moisture, "last_watered": self._last_watered, "status": "Idle"}

        # Enforce configurable watering window (applies to all zones, seedling or not)
        current_hour = dt_util.now().hour
        start = self._effective_window_start_hour
        end = self._effective_window_end_hour
        if not (start <= current_hour < end):
            return {**base, "status": f"Idle — outside watering window ({start:02d}:00–{end:02d}:00)"}

        # Guard: watered recently by us
        min_interval = self.config.get(CONF_MIN_INTERVAL, DEFAULT_MIN_INTERVAL)
        if self._last_watered:
            age_min = (dt_util.utcnow() - self._last_watered).total_seconds() / 60
            if age_min < min_interval:
                return {**base, "status": f"Idle — watered {int(age_min)} min ago"}

        # Guard: valve currently on or recently run
        # Only apply recency check if we saw the valve go ON in this HA session —
        # avoids false positives from the unavailable→off transition at startup.
        valve_state = self.hass.states.get(self.config[CONF_VALVE_SWITCH])
        if valve_state and valve_state.state == "unavailable":
            return {**base, "status": "Skipped — valve unavailable (Yardian offline?)"}
        if valve_state:
            if valve_state.state == "on":
                self._valve_seen_on = True
                return {**base, "status": "Idle — valve currently running"}
            if self._valve_seen_on:
                valve_closed_at = valve_state.last_changed
                # Allow re-evaluation once every configured soil sensor has reported
                # at least one reading after the valve closed. This naturally gates
                # re-watering to one poll cycle (≈15 min) without a fixed timer,
                # and still allows multiple runs in the same window when soil is dry.
                sensors = self.config.get(CONF_SOIL_SENSORS, [])
                sensor_polled_since_close = any(
                    (s := self.hass.states.get(eid)) is not None
                    and s.last_updated > valve_closed_at
                    for eid in sensors
                ) if sensors else (
                    # Sensor-free zones: fall back to a single poll interval (15 min)
                    (dt_util.utcnow() - valve_closed_at).total_seconds() / 60 >= 15
                )
                if not sensor_polled_since_close:
                    elapsed = int((dt_util.utcnow() - valve_closed_at).total_seconds() / 60)
                    return {**base, "status": f"Idle — waiting for sensor poll after watering ({elapsed} min ago)"}
                self._valve_seen_on = False  # sensor has polled; reset for next cycle

        # Motion check
        motion_entity = self.config.get(CONF_MOTION_SENSOR)
        if motion_entity:
            motion_state = self.hass.states.get(motion_entity)
            if motion_state and motion_state.state == "on":
                self._notify(
                    f"irrigation_{self.zone_name}_session",
                    f"Someone is in the {self.zone_name.replace('_', ' ')} zone — watering deferred.",
                )
                return {**base, "status": "Deferred — motion detected"}

        # Decision
        threshold = self._effective_threshold
        sensor_required = self.config.get(CONF_SENSOR_REQUIRED, True)

        # Sensor-free zones (drip/trees) use peer trend inference instead of decide()
        if not sensor_required:
            return await self._decide_sensor_free(base, wind, precip)

        decision = decide(moisture, threshold, trend, precip, wind, sensor_required)

        if decision in ("WATER", "MONITOR"):
            if self._watering_lock.locked():
                return {**base, "status": "Watering in progress"}
            max_dur = self._effective_max_duration
            fallback = int(self.config.get(CONF_FALLBACK_DURATION, DEFAULT_FALLBACK_DURATION))
            duration = calibrated_duration(
                moisture or 0, threshold + 5, self._calibration, fallback, max_dur
            )
            budget = domain_data.get("daily_budget_gallons", DEFAULT_DAILY_BUDGET_GALLONS)
            if budget > 0.0:
                flow = self._effective_flow_rate
                used = domain_data.get("daily_used_gallons", 0.0)
                remaining_gal = budget - used
                if remaining_gal <= 0:
                    msg = f"Daily water budget exhausted ({used:.0f}/{budget:.0f} gal used)."
                    self._notify(f"irrigation_{self.zone_name}_session", msg)
                    return {**base, "status": f"Skipped — budget exhausted ({used:.0f}/{budget:.0f} gal)"}
                remaining_min = remaining_gal / flow
                if duration > remaining_min:
                    duration = max(1, int(remaining_min))
            self.hass.async_create_task(self._water_zone(duration, moisture, decision))
            trend_note = f", trend {trend:+.2f}%/h" if trend is not None else ""
            m_note = f" (soil {moisture:.0f}%{trend_note})" if moisture is not None else ""
            status = f"Watering — {duration} min{m_note}"
        elif decision == "SKIP":
            rain_note = f", {precip:.2f} in rain" if precip >= 0.05 else ""
            if precip >= 0.15 and moisture is not None and moisture > 85:
                status = f"Skipped — {precip:.2f} in rain forecast, soil {moisture:.0f}%"
                msg = f"Skipping — {precip:.2f} in of rain in the forecast and soil is already at {moisture:.0f}%."
            elif moisture is not None:
                status = f"Skipped — soil {moisture:.0f}% ≥ {threshold:.0f}%{rain_note}"
                msg = f"Soil is at {moisture:.0f}% — above the {threshold:.0f}% threshold.{' Rain: ' + f'{precip:.2f} in.' if precip >= 0.05 else ''}"
            else:
                status = f"Skipped{rain_note}"
                msg = "Soil adequate — skipping."
            self._notify(f"irrigation_{self.zone_name}_session", msg)
        elif decision == "DEFER_WIND":
            self._notify(
                f"irrigation_{self.zone_name}_session",
                f"Deferred — wind at {wind:.0f} mph (limit: 25 mph).",
            )
            status = f"Deferred — wind {wind:.0f} mph"
        else:
            status = "Idle"

        return {**base, "status": status}

    # --- Watering ---

    async def _water_zone(self, duration_min: int, soil_before: float | None, reason: str) -> None:
        valve = self.config[CONF_VALVE_SWITCH]
        valve_state = self.hass.states.get(valve)
        if valve_state is None or valve_state.state == "unavailable":
            _LOGGER.warning("%s: valve %s is %s — skipping watering", self.zone_name, valve,
                            "not found" if valve_state is None else "unavailable")
            return
        zone_label = self.zone_name.replace("_", " ").title()
        cycles = max(1, self._effective_soak_cycles)
        pause_min = self._effective_soak_pause_minutes
        # Distribute total duration evenly across cycles (integer minutes, at least 1 per cycle)
        cycle_min = max(1, duration_min // cycles)
        total_actual = cycle_min * cycles

        async with self._watering_lock:
            if cycles > 1:
                _LOGGER.info(
                    "%s: soak/cycle — %d × %d min with %d min pauses (%s)",
                    self.zone_name, cycles, cycle_min, pause_min, reason,
                )
            else:
                _LOGGER.info("%s: opening valve for %d min (%s)", self.zone_name, cycle_min, reason)

            self._last_watered = dt_util.utcnow()
            self._soil_before = soil_before
            self._last_duration = total_actual
            self.async_update_listeners()

            soil_msg = f" Soil was at {soil_before:.0f}%." if soil_before is not None else ""
            if cycles > 1:
                self._notify(
                    f"irrigation_{self.zone_name}_session",
                    f"Watering {zone_label}: {cycles} × {cycle_min} min with {pause_min}-min soak pauses.{soil_msg}",
                )
            else:
                self._notify(
                    f"irrigation_{self.zone_name}_session",
                    f"Watering {zone_label} for {cycle_min} min.{soil_msg}",
                )

            gallons_per_cycle = cycle_min * self._effective_flow_rate
            for i in range(cycles):
                try:
                    await self.hass.services.async_call(
                        "switch", "turn_on", {"entity_id": valve}, blocking=True
                    )
                    await asyncio.sleep(cycle_min * 60)
                finally:
                    await self.hass.services.async_call(
                        "switch", "turn_off", {"entity_id": valve}, blocking=True
                    )
                    _LOGGER.info("%s: valve closed (cycle %d/%d)", self.zone_name, i + 1, cycles)

                # Accumulate usage per cycle so budget is updated incrementally
                d = self.hass.data.setdefault(DOMAIN, {})
                if not d.get("water_meter_entity"):
                    d["daily_used_gallons"] = d.get("daily_used_gallons", 0.0) + gallons_per_cycle

                if i < cycles - 1:
                    _LOGGER.info(
                        "%s: soak pause %d min before cycle %d/%d",
                        self.zone_name, pause_min, i + 2, cycles,
                    )
                    await asyncio.sleep(pause_min * 60)

        if soil_before is not None:
            async_call_later(self.hass, CALIBRATION_FOLLOWUP_SECONDS, self._calibration_followup)

    @callback
    def _calibration_followup(self, _now=None) -> None:
        soil_after = self._read_soil_moisture()
        if soil_after is None or self._soil_before is None or self._last_duration == 0:
            _LOGGER.debug(
                "%s: calibration followup skipped — missing data (soil_after=%s, soil_before=%s, duration=%s)",
                self.zone_name, soil_after, self._soil_before, self._last_duration,
            )
            return
        rise = soil_after - self._soil_before
        # Allow up to -1% tolerance for sensor noise and fast-draining soils.
        # Only skip if moisture genuinely didn't absorb (sensor may read slightly
        # below starting value due to surface evaporation in heat/wind).
        if rise < -1.0:
            _LOGGER.debug(
                "%s: calibration skipped — soil dropped %.1f%% (before=%.1f, after=%.1f); "
                "possible fast-draining soil or sensor in unwatered spot",
                self.zone_name, rise, self._soil_before, soil_after,
            )
            return
        if rise <= 0:
            _LOGGER.debug(
                "%s: calibration skipped — no measurable soil rise (before=%.1f, after=%.1f)",
                self.zone_name, self._soil_before, soil_after,
            )
            return
        rate = round(rise / self._last_duration, 4)
        if self._calibration is None:
            self._calibration = rate
        else:
            self._calibration = round(0.8 * self._calibration + 0.2 * rate, 4)
        _LOGGER.info(
            "%s: calibration updated → %.4f %%/min (rise=%.1f%% over %d min)",
            self.zone_name, self._calibration, rise, self._last_duration,
        )
        # Bug fix: update coordinator.data immediately so native_value reflects
        # the new calibration without waiting for the next 15-min poll.
        if self.data is not None:
            self.data["calibration"] = self._calibration
        self.async_update_listeners()
        # Persist to Store so calibration survives HA restarts even if entity
        # state is briefly unknown (avoids the RestoreEntity timing race).
        self.hass.async_create_task(self._persist_calibration())

    def force_calibration_followup(self) -> None:
        """Public entry point for the force_calibration service.

        Runs the calibration followup immediately using the current soil reading.
        Useful after a manual watering run to verify the sensor detects moisture rise.
        If _soil_before is None (after a restart), uses current moisture as both
        before and after so the result shows a 0-rise (expected — logs will explain).
        """
        _LOGGER.info("%s: force_calibration_followup called manually", self.zone_name)
        self._calibration_followup()

    async def water_now(self, duration_min: int) -> None:
        """Public entry point for the water_zone service."""
        moisture = self._read_soil_moisture()
        self.hass.async_create_task(self._water_zone(duration_min, moisture, "manual"))

    # --- Weather + ET ---

    async def _fetch_weather(self) -> dict | None:
        weather_entity = self.hass.data.get(DOMAIN, {}).get("weather_entity", DEFAULT_WEATHER_ENTITY)
        try:
            result = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "daily"},
                blocking=True,
                return_response=True,
            )
            forecasts = (result or {}).get(weather_entity, {}).get("forecast", [])
            return forecasts[0] if forecasts else None
        except Exception as err:
            _LOGGER.debug("%s: weather unavailable (%s): %s", self.zone_name, weather_entity, err)
            return None

    def _compute_et(self, forecast: dict) -> float | None:
        try:
            temp_high = float(forecast["temperature"])
            temp_low = float(forecast["templow"])
            doy = dt_util.now().timetuple().tm_yday
            lat = self.hass.config.latitude
            kc = float(self.config.get(CONF_CROP_COEFFICIENT, DEFAULT_CROP_COEFFICIENT))
            et_ref = hargreaves_et(temp_high, temp_low, lat, doy)
            return round(et_ref * kc, 2)
        except Exception:
            return None

    # --- Soil moisture + trend ---

    def _read_soil_moisture(self) -> float | None:
        sensors = self.config.get(CONF_SOIL_SENSORS, [])
        if not sensors:
            return None
        readings = []
        stale_cutoff = dt_util.utcnow() - timedelta(hours=STALE_SENSOR_HOURS)
        for entity_id in sensors:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                continue
            if state.last_updated < stale_cutoff:
                _LOGGER.warning("%s: %s stale (last updated %s)", self.zone_name, entity_id, state.last_updated)
                continue
            try:
                readings.append(float(state.state))
            except ValueError:
                pass
        if readings:
            result = round(sum(readings) / len(readings), 1)
            self._last_moisture = result  # cache for startup fallback
            return result
        # Return last cached value when sensors are temporarily unavailable (e.g. HA startup)
        return self._last_moisture

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
            _LOGGER.warning("%s: trend query failed: %s", self.zone_name, err)
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
        return round(slope * 3600, 3)

    # --- Sensor-free zone (drip/trees) decision ---

    async def _decide_sensor_free(self, base: dict, wind: float, precip: float) -> dict:
        """Decision path for zones with no soil sensor. Uses peer trend + interval floor."""
        zone_label = self.zone_name.replace("_", " ").title()
        interval = self._effective_water_interval
        fallback = int(self.config.get(CONF_FALLBACK_DURATION, DEFAULT_FALLBACK_DURATION))

        if wind > 25:
            self._notify(f"irrigation_{self.zone_name}_session", f"Deferred — wind at {wind:.0f} mph.")
            return {**base, "status": f"Deferred — wind {wind:.0f} mph"}

        if precip >= 0.15:
            self._notify(f"irrigation_{self.zone_name}_session", f"Skipped — {precip:.2f} in of rain in the forecast.")
            return {**base, "status": f"Skipped — {precip:.2f} in rain forecast"}

        days_since = (
            (dt_util.utcnow() - self._last_watered).total_seconds() / 86400
            if self._last_watered else 999.0
        )

        peer_trend = self._infer_trend_from_peers()

        # Drying fast + at least half the interval has passed → water early
        if peer_trend is not None and peer_trend < PEER_TREND_DRYING_THRESHOLD and days_since >= interval / 2:
            reason = f"peers drying at {peer_trend:+.2f}%/h, {days_since:.1f}d since last watering"
            should_water = True
        # Full interval elapsed (regardless of peer trend)
        elif days_since >= interval:
            reason = f"{days_since:.1f}d since last watering"
            should_water = True
        else:
            remaining = interval - days_since
            peer_note = f", peer trend {peer_trend:+.2f}%/h" if peer_trend is not None else " (no peer data)"
            return {**base, "status": f"Idle — {remaining:.1f}d until next watering{peer_note}"}

        if self._watering_lock.locked():
            return {**base, "status": "Watering in progress"}

        self.hass.async_create_task(self._water_zone(fallback, None, f"sensor-free: {reason}"))
        return {**base, "status": f"Watering — {fallback} min"}

    async def _init_last_watered_from_history(self) -> None:
        """Seed last_watered from valve switch recorder history when no restore state exists."""
        valve = self.config.get(CONF_VALVE_SWITCH)
        if not valve:
            return
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states

        start = dt_util.utcnow() - timedelta(days=30)
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                get_significant_states, self.hass, start, None, [valve]
            )
        except Exception as err:
            _LOGGER.debug("%s: valve history query failed: %s", self.zone_name, err)
            return

        # Walk forward through history; record the last off timestamp that followed an on.
        saw_on = False
        last_off_after_on: datetime | None = None
        for s in states.get(valve, []):
            if s.state == "on":
                saw_on = True
            elif s.state == "off" and saw_on:
                last_off_after_on = s.last_changed
                saw_on = False

        if last_off_after_on:
            self._last_watered = last_off_after_on
            _LOGGER.debug(
                "%s: seeded last_watered from valve history: %s", self.zone_name, last_off_after_on
            )

    async def _init_moisture_from_history(self) -> float | None:
        """Seed moisture from the most recent recorder reading when sensors haven't loaded yet."""
        sensors = self.config.get(CONF_SOIL_SENSORS, [])
        if not sensors:
            return None
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states

        start = dt_util.utcnow() - timedelta(hours=STALE_SENSOR_HOURS)
        readings = []
        for entity_id in sensors:
            try:
                states = await get_instance(self.hass).async_add_executor_job(
                    get_significant_states, self.hass, start, None, [entity_id]
                )
                for s in reversed(states.get(entity_id, [])):
                    if s.state not in ("unknown", "unavailable"):
                        readings.append(float(s.state))
                        break
            except Exception as err:
                _LOGGER.debug("%s: moisture history query failed for %s: %s", self.zone_name, entity_id, err)
        return round(sum(readings) / len(readings), 1) if readings else None

    def _infer_trend_from_peers(self) -> float | None:
        """Average moisture trend from zones that have real soil sensors."""
        trends = []
        for entry_id, coord in self.hass.data.get(DOMAIN, {}).items():
            if entry_id == self.entry.entry_id:
                continue
            if not isinstance(coord, AdaptiveIrrigationCoordinator):
                continue
            if not coord.config.get(CONF_SENSOR_REQUIRED, True):
                continue  # skip other sensor-free zones
            if coord.data and coord.data.get("trend") is not None:
                trends.append(coord.data["trend"])
        return round(sum(trends) / len(trends), 3) if trends else None

    # --- Notification helper ---

    def _notify(self, notification_id: str, message: str) -> None:
        self.hass.async_create_task(
            self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": notification_id,
                    "title": f"Irrigation — {self.zone_name.replace('_', ' ').title()}",
                    "message": message,
                },
            )
        )
