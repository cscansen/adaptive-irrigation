from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CALIBRATION_DOWN_WEIGHT,
    CALIBRATION_MAX_RATE,
    CALIBRATION_MIN_RATE,
    CALIBRATION_MIN_RUN_MINUTES,
    CALIBRATION_PEAK_TIMEOUT_HOURS,
    CALIBRATION_SETTLE_MINUTES,
    COOLING_HARD_STOP_HOUR,
    COOLING_POST_WATER_LOCKOUT_MINUTES,
    COOLING_RISE_MIN_RATE,
    COOLING_TREND_MINUTES,
    CONF_COOLING_DURATION,
    CONF_COOLING_ENABLED,
    CONF_COOLING_MAX_RUNS_PER_DAY,
    CONF_COOLING_MIN_INTERVAL,
    CONF_COOLING_MOISTURE_CEILING,
    CONF_COOLING_TEMP_THRESHOLD,
    CONF_COOLING_WIND_LIMIT,
    CONF_COOLING_WINDOW_END_HOUR,
    CONF_COOLING_WINDOW_START_HOUR,
    CONF_FILL_TARGET,
    CONF_REFILL_POINT,
    CONF_SOIL_TEMP_SENSOR,
    DEFAULT_COOLING_DURATION,
    DEFAULT_COOLING_ENABLED,
    DEFAULT_COOLING_MAX_RUNS_PER_DAY,
    DEFAULT_COOLING_MIN_INTERVAL,
    DEFAULT_COOLING_MOISTURE_CEILING,
    DEFAULT_COOLING_TEMP_THRESHOLD,
    DEFAULT_COOLING_WIND_LIMIT,
    DEFAULT_COOLING_WINDOW_END_HOUR,
    DEFAULT_COOLING_WINDOW_START_HOUR,
    DEFAULT_FILL_TARGET,
    DEFAULT_REFILL_POINT,
    DRYDOWN_LOCKOUT_HOURS,
    MIN_CYCLE_MINUTES,
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
from .logic import (
    calibrated_duration,
    decide,
    hargreaves_et,
    soak_plan,
    should_cool,
    update_calibration,
)

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
        self._valve_seen_on: bool = False  # set when we open the valve, or observe someone else's run

        # --- Cooling (syringing) state ---
        self._last_cooling: datetime | None = None
        self._cooling_runs_today: int = 0
        self._cooling_date: str | None = None
        self._last_cooling_delta: float | None = None
        self._cooling_lock = asyncio.Lock()
        self._cooling_status: str | None = None
        self._soil_temp: float | None = None

        # --- Dry-down / calibration state ---
        self._last_soak_end: datetime | None = None
        self._drydown_start: datetime | None = None
        self._drydown_start_moisture: float | None = None
        self._last_drydown_hours: float | None = None
        # Peak-tracking replaces the old fixed +30 min sample. The probes keep
        # climbing for ~4 h after an application, so a single early read saw
        # under half the eventual rise.
        self._cal_watch_active: bool = False
        self._cal_peak: float | None = None
        self._cal_peak_at: datetime | None = None
        self._cal_deadline: datetime | None = None
        self._cal_voided_reason: str | None = None

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
        self._live_refill_point: float | None = None
        self._live_fill_target: float | None = None
        self._live_fallback_duration: int | None = None
        self._cooling_enabled: bool | None = None
        self._live_cooling_threshold: float | None = None
        self._live_cooling_duration: int | None = None

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

    @property
    def _effective_refill_point(self) -> float:
        """Moisture level at which the zone has earned its next soak.

        Seedling mode still short-circuits to its own threshold — seedlings
        have no root system to deepen and must not be dried down.
        """
        if self._effective_seedling_mode:
            return self._effective_threshold
        if self._live_refill_point is not None:
            return self._live_refill_point
        return float(self.config.get(CONF_REFILL_POINT, DEFAULT_REFILL_POINT))

    @property
    def _effective_fill_target(self) -> float:
        if self._effective_seedling_mode:
            return self._effective_threshold + 5
        if self._live_fill_target is not None:
            return self._live_fill_target
        return float(self.config.get(CONF_FILL_TARGET, DEFAULT_FILL_TARGET))

    @property
    def _effective_fallback_duration(self) -> int:
        if self._live_fallback_duration is not None:
            return self._live_fallback_duration
        return int(self.config.get(CONF_FALLBACK_DURATION, DEFAULT_FALLBACK_DURATION))

    # --- Cooling effective values ---

    @property
    def _effective_cooling_enabled(self) -> bool:
        if self._cooling_enabled is not None:
            return self._cooling_enabled
        return bool(self.config.get(CONF_COOLING_ENABLED, DEFAULT_COOLING_ENABLED))

    @property
    def _effective_cooling_threshold(self) -> float:
        if self._live_cooling_threshold is not None:
            return self._live_cooling_threshold
        return float(self.config.get(CONF_COOLING_TEMP_THRESHOLD, DEFAULT_COOLING_TEMP_THRESHOLD))

    @property
    def _effective_cooling_duration(self) -> int:
        if self._live_cooling_duration is not None:
            return self._live_cooling_duration
        return int(self.config.get(CONF_COOLING_DURATION, DEFAULT_COOLING_DURATION))

    @property
    def _effective_cooling_window(self) -> tuple[int, int]:
        d = self.hass.data.get(DOMAIN, {})
        start = int(d.get("cooling_window_start_hour", DEFAULT_COOLING_WINDOW_START_HOUR))
        end = int(d.get("cooling_window_end_hour", DEFAULT_COOLING_WINDOW_END_HOUR))
        # Hard stop is enforced in code, not left to configuration: a canopy
        # left wet overnight invites fungal disease.
        return start, min(end, COOLING_HARD_STOP_HOUR)

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

    def set_live_refill_point(self, value: float) -> None:
        self._live_refill_point = value

    def set_live_fill_target(self, value: float) -> None:
        self._live_fill_target = value

    def set_live_fallback_duration(self, value: int) -> None:
        self._live_fallback_duration = value

    def set_cooling_enabled(self, enabled: bool) -> None:
        self._cooling_enabled = enabled

    def set_live_cooling_threshold(self, value: float) -> None:
        self._live_cooling_threshold = value

    def set_live_cooling_duration(self, value: int) -> None:
        self._live_cooling_duration = value

    # --- Main poll ---

    async def _async_update_data(self) -> dict:
        moisture = self._read_soil_moisture()
        trend = await self._read_moisture_trend()
        soil_temp = self._read_soil_temp()
        temp_rise = await self._read_soil_temp_trend()
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
            "soil_temp": soil_temp,
            "soil_temp_rise": temp_rise,
            "et_today": et_today,
            "precip": precip,
            "wind": wind,
            "last_watered": self._last_watered,
            "calibration": self._calibration,
            "seedling_expires": self._seedling_expires,
            "refill_point": self._effective_refill_point,
            "fill_target": self._effective_fill_target,
            "cooling_runs_today": self._cooling_runs_today,
            "last_cooling": self._last_cooling,
            "last_cooling_delta": self._last_cooling_delta,
            "cooling_status": self._cooling_status,
            "last_drydown_hours": self._last_drydown_hours,
            "days_to_refill": self._project_days_to_refill(moisture, trend),
        }

        domain_data = self.hass.data.setdefault(DOMAIN, {})

        # Reset the per-day cooling counter at local midnight.
        today_local = dt_util.now().date().isoformat()
        if self._cooling_date != today_local:
            self._cooling_date = today_local
            self._cooling_runs_today = 0
            base["cooling_runs_today"] = 0

        # Advance the post-soak peak watch. Runs regardless of window or enable
        # state — an in-flight measurement should finish even if the zone is
        # switched off part-way through.
        self._calibration_tick(moisture)
        base["calibration"] = self._calibration

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

        # Master switch and water restriction gate everything, cooling included.
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

        # Detect runs we did not start (the irrigation controller's own
        # schedules). Left unnoticed these get credited to our own runs and
        # corrupt the calibration.
        self._detect_foreign_run()

        # --- Cooling evaluation ---
        # Deliberately evaluated before the watering-window guard: the cooling
        # window (midday heat) is disjoint from the watering window (early
        # morning), so anything below that guard would never run.
        #
        # Cooling is independent of the zone's Auto Watering switch — it is a
        # heat-stress intervention, not irrigation, and has its own enable.
        cooling_result = await self._evaluate_cooling(base, moisture, soil_temp, temp_rise, wind, precip)
        if cooling_result is not None:
            return cooling_result

        if not self._auto_enabled:
            return {**base, "status": "Disabled"}

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
                # Wait for the probe to show a genuine RISE before considering
                # another run. The probes report on change only, so "the state
                # updated" is not evidence of a fresh reading — before 0.8.0
                # this accepted a downward tick (the soil drying out) as
                # confirmation that watering had registered.
                sensors = self.config.get(CONF_SOIL_SENSORS, [])
                if sensors:
                    responded = self._moisture_rose_since(valve_closed_at)
                else:
                    # Sensor-free zones: fall back to a single poll interval.
                    responded = (dt_util.utcnow() - valve_closed_at).total_seconds() / 60 >= 15
                if not responded:
                    elapsed = int((dt_util.utcnow() - valve_closed_at).total_seconds() / 60)
                    return {**base, "status": f"Idle — waiting for soil response after watering ({elapsed} min ago)"}
                self._valve_seen_on = False  # soil responded; reset for next cycle

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
        refill_point = self._effective_refill_point
        fill_target = self._effective_fill_target
        sensor_required = self.config.get(CONF_SENSOR_REQUIRED, True)

        # Sensor-free zones (drip/trees) use peer trend inference instead of decide()
        if not sensor_required:
            return await self._decide_sensor_free(base, wind, precip)

        # Dry-down lockout: after a soak the probes need hours to finish
        # responding. Re-evaluating sooner means acting on a reading that
        # hasn't caught up, which is how the old build managed five runs in
        # one morning while the probe never moved.
        in_lockout, lockout_note = self._in_drydown_lockout()

        decision = decide(moisture, refill_point, precip, wind, in_lockout)

        if decision == "WATER":
            if self._watering_lock.locked():
                return {**base, "status": "Watering in progress"}
            max_dur = self._effective_max_duration
            fallback = self._effective_fallback_duration
            duration = calibrated_duration(
                moisture or 0, fill_target, self._calibration, fallback, max_dur
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
            m_note = f" (soil {moisture:.0f}% → target {fill_target:.0f}%)" if moisture is not None else ""
            status = f"Soaking — {duration} min{m_note}"
        elif decision == "LOCKOUT":
            status = f"Idle — {lockout_note}"
        elif decision == "SKIP":
            if precip >= 0.15 and moisture is not None and moisture <= refill_point:
                status = f"Skipped — {precip:.2f} in rain forecast, soil {moisture:.0f}%"
                msg = f"Due a soak at {moisture:.0f}% but {precip:.2f} in of rain is forecast — letting the weather do it."
                self._notify(f"irrigation_{self.zone_name}_session", msg)
            elif moisture is not None:
                days = base.get("days_to_refill")
                eta = f", ~{days:.1f}d to refill" if days is not None else ""
                status = f"Idle — soil {moisture:.0f}% above refill {refill_point:.0f}%{eta}"
            else:
                status = "Idle — no soil reading"
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
        pause_min = self._effective_soak_pause_minutes
        # Distribute the remainder across cycles rather than discarding it, and
        # refuse to split a run too short to be worth splitting.
        plan = soak_plan(duration_min, self._effective_soak_cycles, MIN_CYCLE_MINUTES)
        if not plan:
            _LOGGER.warning("%s: zero-length watering request — ignored", self.zone_name)
            return
        cycles = len(plan)
        total_actual = sum(plan)

        async with self._watering_lock:
            if cycles > 1:
                _LOGGER.info(
                    "%s: soak/cycle — %s min with %d min pauses, %d min total (%s)",
                    self.zone_name, "+".join(str(m) for m in plan), pause_min, total_actual, reason,
                )
            else:
                _LOGGER.info("%s: opening valve for %d min (%s)", self.zone_name, total_actual, reason)

            self._soil_before = soil_before
            self._last_duration = total_actual
            # Mark that a run of ours is underway so the post-water gate and the
            # foreign-run detector both attribute it correctly. Before 0.8.0
            # this was only set when a 15-minute poll happened to catch the
            # valve open, which a short run never survives.
            self._valve_seen_on = True
            self.async_update_listeners()

            soil_msg = f" Soil was at {soil_before:.0f}%." if soil_before is not None else ""
            if cycles > 1:
                self._notify(
                    f"irrigation_{self.zone_name}_session",
                    f"Soaking {zone_label}: {' + '.join(f'{m} min' for m in plan)} "
                    f"with {pause_min}-min pauses ({total_actual} min total).{soil_msg}",
                )
            else:
                self._notify(
                    f"irrigation_{self.zone_name}_session",
                    f"Soaking {zone_label} for {total_actual} min.{soil_msg}",
                )

            flow = self._effective_flow_rate
            for i, cycle_min in enumerate(plan):
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
                    d["daily_used_gallons"] = d.get("daily_used_gallons", 0.0) + cycle_min * flow

                if i < cycles - 1:
                    _LOGGER.info(
                        "%s: soak pause %d min before cycle %d/%d",
                        self.zone_name, pause_min, i + 2, cycles,
                    )
                    await asyncio.sleep(pause_min * 60)

        # Stamp completion, not start. The interval and lockout clocks should
        # run from when the water stopped, not from when a 90-minute
        # cycle-and-soak began.
        self._last_watered = dt_util.utcnow()
        self._last_soak_end = self._last_watered
        self._drydown_start = self._last_watered
        self._drydown_start_moisture = None  # captured once the probe peaks
        self.async_update_listeners()

        if soil_before is not None:
            self._begin_calibration_watch()

    def _begin_calibration_watch(self) -> None:
        """Start following the probe to its peak after a soak.

        Replaces the old single sample at +30 min. Measured on this system, a
        15-minute application was still raising the probe four hours later
        (38% → 48%), so a +30 min read captured well under half the response
        and systematically mis-taught the estimator.
        """
        self._cal_watch_active = True
        self._cal_peak = self._read_soil_moisture()
        self._cal_peak_at = dt_util.utcnow()
        self._cal_deadline = dt_util.utcnow() + timedelta(hours=CALIBRATION_PEAK_TIMEOUT_HOURS)
        self._cal_voided_reason = None
        _LOGGER.info(
            "%s: watching for soil peak after %d min run (start %.1f%%, timeout %dh)",
            self.zone_name, self._last_duration, self._cal_peak or -1, CALIBRATION_PEAK_TIMEOUT_HOURS,
        )

    def void_calibration_watch(self, reason: str) -> None:
        """Abandon the in-flight calibration sample.

        Called when something we did not initiate puts water on the zone. The
        pre-0.8.0 code had no such notion: an independent controller run inside
        the follow-up window was credited to our own (much shorter) run, which
        is how this system arrived at rates of 2.75 and 4.16 %/min — physically
        impossible figures that then prescribed 3-minute soaks.
        """
        if not self._cal_watch_active:
            return
        self._cal_watch_active = False
        self._cal_voided_reason = reason
        _LOGGER.info("%s: calibration sample voided — %s", self.zone_name, reason)

    def _calibration_tick(self, moisture: float | None) -> None:
        """Advance the peak watch. Called once per poll while active."""
        if not self._cal_watch_active:
            return
        now = dt_util.utcnow()

        if moisture is not None:
            if self._cal_peak is None or moisture > self._cal_peak:
                self._cal_peak = moisture
                self._cal_peak_at = now
                return  # still climbing

        settled = (
            self._cal_peak_at is not None
            and (now - self._cal_peak_at).total_seconds() / 60 >= CALIBRATION_SETTLE_MINUTES
        )
        timed_out = self._cal_deadline is not None and now >= self._cal_deadline
        if not (settled or timed_out):
            return

        self._cal_watch_active = False
        if self._cal_peak is None or self._soil_before is None or self._last_duration == 0:
            _LOGGER.debug("%s: calibration skipped — incomplete sample", self.zone_name)
            return

        rise = self._cal_peak - self._soil_before
        new_rate, reason = update_calibration(
            self._calibration,
            rise,
            self._last_duration,
            CALIBRATION_MIN_RUN_MINUTES,
            CALIBRATION_DOWN_WEIGHT,
            CALIBRATION_MIN_RATE,
            CALIBRATION_MAX_RATE,
        )

        # The peak is also where dry-down begins — record it for the deferred
        # root-training work, which needs cycle length against real weather.
        self._drydown_start = self._cal_peak_at or now
        self._drydown_start_moisture = self._cal_peak

        if new_rate is None:
            _LOGGER.info("%s: calibration unchanged — %s", self.zone_name, reason)
            return

        self._calibration = new_rate
        _LOGGER.info(
            "%s: calibration → %.4f %%/min (%s, peak %.1f%% from %.1f%%)",
            self.zone_name, new_rate, reason, self._cal_peak, self._soil_before,
        )
        if self.data is not None:
            self.data["calibration"] = new_rate
        self.async_update_listeners()
        # Persist to Store so calibration survives HA restarts even if entity
        # state is briefly unknown (avoids the RestoreEntity timing race).
        self.hass.async_create_task(self._persist_calibration())

    def force_calibration_followup(self) -> None:
        """Public entry point for the force_calibration service.

        Forces the in-flight peak watch to resolve now using the highest
        reading seen so far, rather than waiting for it to settle.
        """
        _LOGGER.info("%s: force_calibration_followup called manually", self.zone_name)
        if not self._cal_watch_active:
            _LOGGER.info("%s: no calibration watch in flight — nothing to resolve", self.zone_name)
            return
        self._cal_deadline = dt_util.utcnow()
        self._calibration_tick(self._read_soil_moisture())

    async def water_now(self, duration_min: int) -> None:
        """Public entry point for the water_zone service."""
        moisture = self._read_soil_moisture()
        self.hass.async_create_task(self._water_zone(duration_min, moisture, "manual"))

    # --- Cooling (syringing) ---

    async def _evaluate_cooling(
        self,
        base: dict,
        moisture: float | None,
        soil_temp: float | None,
        temp_rise: float | None,
        wind: float,
        precip: float,
    ) -> dict | None:
        """Evaluate heat-stress cooling. Returns a status dict, or None to fall
        through to the irrigation logic.

        Syringing applies a small amount of water to knock the top off a
        root-zone temperature spike. It is not irrigation and must not touch
        last_watered, the calibration loop, or the dry-down clock.
        """
        if not self.config.get(CONF_SOIL_TEMP_SENSOR):
            return None
        if not self.config.get(CONF_SENSOR_REQUIRED, True):
            return None  # beds/drip — syringing is a turf practice
        if not self._effective_cooling_enabled:
            return None
        if not self.hass.data.get(DOMAIN, {}).get("cooling_enabled", True):
            return None

        start_h, end_h = self._effective_cooling_window
        if not (start_h <= dt_util.now().hour < end_h):
            return None

        since_cool = (
            (dt_util.utcnow() - self._last_cooling).total_seconds() / 60
            if self._last_cooling else None
        )
        since_water = (
            (dt_util.utcnow() - self._last_watered).total_seconds() / 60
            if self._last_watered else None
        )

        run, reason = should_cool(
            soil_temp=soil_temp,
            threshold=self._effective_cooling_threshold,
            temp_rise_rate=temp_rise,
            rise_min_rate=COOLING_RISE_MIN_RATE,
            moisture=moisture,
            moisture_ceiling=float(
                self.config.get(CONF_COOLING_MOISTURE_CEILING, DEFAULT_COOLING_MOISTURE_CEILING)
            ),
            wind_mph=wind,
            wind_limit=float(
                self.hass.data.get(DOMAIN, {}).get("cooling_wind_limit", DEFAULT_COOLING_WIND_LIMIT)
            ),
            precip_in=precip,
            runs_today=self._cooling_runs_today,
            max_runs=int(
                self.hass.data.get(DOMAIN, {}).get(
                    "cooling_max_runs_per_day", DEFAULT_COOLING_MAX_RUNS_PER_DAY
                )
            ),
            minutes_since_cooling=since_cool,
            min_interval=float(
                self.hass.data.get(DOMAIN, {}).get(
                    "cooling_min_interval", DEFAULT_COOLING_MIN_INTERVAL
                )
            ),
            minutes_since_watering=since_water,
            post_water_lockout=COOLING_POST_WATER_LOCKOUT_MINUTES,
        )

        self._cooling_status = reason

        if not run:
            temp_note = f"{soil_temp:.0f}°F — " if soil_temp is not None else ""
            return {**base, "cooling_status": reason, "status": f"Monitoring heat ({temp_note}{reason})"}

        if self._watering_lock.locked() or self._cooling_lock.locked():
            return {**base, "cooling_status": reason, "status": "Busy — run already in progress"}

        duration = self._effective_cooling_duration
        self.hass.async_create_task(self._cool_zone(duration, soil_temp, reason))
        return {
            **base,
            "cooling_status": reason,
            "status": f"Cooling — {duration} min ({reason})",
        }

    async def _cool_zone(self, duration_min: int, temp_before: float | None, reason: str) -> None:
        """Run a short cooling application and score its effect.

        Scoring is the reason this belongs in Home Assistant rather than the
        irrigation controller: the same system that opens the valve also holds
        the root-zone probe, so every run can be measured instead of assumed.
        """
        valve = self.config[CONF_VALVE_SWITCH]
        valve_state = self.hass.states.get(valve)
        if valve_state is None or valve_state.state == "unavailable":
            _LOGGER.warning("%s: valve unavailable — skipping cooling", self.zone_name)
            return

        zone_label = self.zone_name.replace("_", " ").title()
        async with self._cooling_lock:
            _LOGGER.info(
                "%s: cooling for %d min (%s, root zone %.1f°F)",
                self.zone_name, duration_min, reason, temp_before if temp_before is not None else -1,
            )
            self._last_cooling = dt_util.utcnow()
            self._cooling_runs_today += 1
            self.async_update_listeners()

            try:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": valve}, blocking=True
                )
                await asyncio.sleep(duration_min * 60)
            finally:
                await self.hass.services.async_call(
                    "switch", "turn_off", {"entity_id": valve}, blocking=True
                )

            # Let the probe settle, then score the run.
            await asyncio.sleep(600)
            temp_after = self._read_soil_temp()

        if temp_before is not None and temp_after is not None:
            self._last_cooling_delta = round(temp_after - temp_before, 1)
            _LOGGER.info(
                "%s: cooling delta %+.1f°F (%.1f → %.1f)",
                self.zone_name, self._last_cooling_delta, temp_before, temp_after,
            )
            self._notify(
                f"irrigation_{self.zone_name}_cooling",
                f"Cooled {zone_label} for {duration_min} min — root zone "
                f"{temp_before:.0f}°F → {temp_after:.0f}°F ({self._last_cooling_delta:+.1f}°F).",
            )
        self.async_update_listeners()

    async def cool_now(self, duration_min: int | None = None) -> None:
        """Public entry point for the cool_zone service."""
        duration = duration_min or self._effective_cooling_duration
        self.hass.async_create_task(
            self._cool_zone(duration, self._read_soil_temp(), "manual")
        )

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

    # --- Soil temperature ---

    def _read_soil_temp(self) -> float | None:
        """Current root-zone temperature, or None if not configured/available."""
        entity_id = self.config.get(CONF_SOIL_TEMP_SENSOR)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return self._soil_temp  # last known
        try:
            self._soil_temp = round(float(state.state), 1)
        except ValueError:
            return self._soil_temp
        return self._soil_temp

    async def _read_soil_temp_trend(self) -> float | None:
        """Root-zone temperature rise rate in °F/min over the recent window.

        Cooling arms only while the zone is still heating, so this is what
        lets each zone self-time instead of sharing one fixed clock — a zone
        that peaks at midday and a west exposure that peaks late afternoon
        both get treated on the way up.
        """
        entity_id = self.config.get(CONF_SOIL_TEMP_SENSOR)
        if not entity_id:
            return None

        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states

        start = dt_util.utcnow() - timedelta(minutes=COOLING_TREND_MINUTES)
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                get_significant_states, self.hass, start, None, [entity_id]
            )
        except Exception as err:
            _LOGGER.debug("%s: soil temp trend query failed: %s", self.zone_name, err)
            return None

        readings = []
        for s in states.get(entity_id, []):
            if s.state in ("unknown", "unavailable"):
                continue
            try:
                readings.append((s.last_updated.timestamp(), float(s.state)))
            except ValueError:
                pass
        if len(readings) < 2:
            return None

        (t0, v0), (t1, v1) = readings[0], readings[-1]
        span_min = (t1 - t0) / 60
        if span_min <= 0:
            return None
        return round((v1 - v0) / span_min, 4)

    # --- Dry-down tracking ---

    def _moisture_rose_since(self, since: datetime) -> bool:
        """True if any configured probe has recorded a HIGHER value since `since`.

        The probes report on change only, so a bare last_updated comparison
        (pre-0.8.0) answered "has the value changed", not "has a fresh reading
        arrived" — and accepted the soil drying out as proof that watering had
        registered.
        """
        for entity_id in self.config.get(CONF_SOIL_SENSORS, []):
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                continue
            if state.last_changed <= since:
                continue
            try:
                value = float(state.state)
            except ValueError:
                continue
            if self._soil_before is None or value > self._soil_before:
                return True
        return False

    def _in_drydown_lockout(self) -> tuple[bool, str]:
        """Suppress moisture-driven watering for a period after a soak.

        Deep-and-infrequent depends on actually leaving the zone alone. It also
        guards against the probe lag: for hours after a soak the reading still
        understates what is in the ground.
        """
        if self._last_soak_end is None:
            return False, ""
        elapsed_h = (dt_util.utcnow() - self._last_soak_end).total_seconds() / 3600
        if elapsed_h >= DRYDOWN_LOCKOUT_HOURS:
            return False, ""
        remaining = DRYDOWN_LOCKOUT_HOURS - elapsed_h
        return True, f"drying down ({remaining:.0f}h of lockout left)"

    def _project_days_to_refill(self, moisture: float | None, trend: float | None) -> float | None:
        """Estimate days until the zone reaches its refill point.

        This is what ET is for under the interval model: predicting when the
        next soak falls due, rather than inflating a fill target.
        """
        if moisture is None or trend is None or trend >= 0:
            return None
        refill = self._effective_refill_point
        if moisture <= refill:
            return 0.0
        return round((moisture - refill) / abs(trend) / 24, 1)

    def _detect_foreign_run(self) -> None:
        """Notice valve activity we did not initiate.

        Any other controller sharing these valves (a Yardian schedule, a manual
        run from its app) puts water on the zone that we would otherwise credit
        to ourselves. Void the calibration sample and reset the dry-down clock.
        """
        valve = self.config.get(CONF_VALVE_SWITCH)
        if not valve:
            return
        state = self.hass.states.get(valve)
        if state is None or state.state != "on":
            return
        if self._watering_lock.locked() or self._cooling_lock.locked():
            return  # ours
        _LOGGER.info("%s: valve on but no run of ours in flight — external run", self.zone_name)
        self.void_calibration_watch("external controller ran this zone")
        # Deliberately does NOT touch _last_soak_end. A 15-minute poll cannot
        # tell a brief syringe from a deep soak, and treating every external
        # valve-on as a soak would lock the zone out for 18 h on the strength
        # of a couple of minutes of water. The valve guard and the
        # soil-response guard already cover near-term recency.

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
