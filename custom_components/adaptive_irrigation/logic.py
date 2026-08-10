"""Watering decision engine and ET calculation. No HA dependencies — pure Python."""

import math


def hargreaves_et(temp_max_f: float, temp_min_f: float, lat_deg: float, day_of_year: int) -> float:
    """Return Hargreaves-Samani reference ET in mm/day."""
    temp_max_c = (temp_max_f - 32) * 5 / 9
    temp_min_c = (temp_min_f - 32) * 5 / 9
    temp_mean_c = (temp_max_c + temp_min_c) / 2
    temp_range = max(temp_max_c - temp_min_c, 0)

    lat_rad = math.radians(lat_deg)
    d_r = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    omega_s = math.acos(max(-1, min(1, -math.tan(lat_rad) * math.tan(delta))))
    Ra = (24 * 60 / math.pi) * 0.0820 * d_r * (
        omega_s * math.sin(lat_rad) * math.sin(delta)
        + math.cos(lat_rad) * math.cos(delta) * math.sin(omega_s)
    )
    et0 = 0.0023 * Ra * math.sqrt(temp_range) * (temp_mean_c + 17.8)
    return max(et0, 0.0)


def decide(
    moisture: float | None,
    refill_point: float,
    forecast_precip_in: float,
    wind_mph: float,
    in_drydown_lockout: bool,
) -> str:
    """
    Return one of: WATER, SKIP, DEFER_WIND, LOCKOUT.

    Interval-adaptive: the zone is left alone until it dries to its refill
    point, then soaked deep. The dry-down between soaks is deliberate — it is
    what drives roots downward. Topping up little and often (the pre-0.8.0
    behaviour) keeps roots at the surface.

    Only called for zones with soil sensors. Sensor-free zones are handled by
    coordinator._decide_sensor_free(). Motion is checked by the coordinator
    before calling this function.
    """
    if wind_mph > 25:
        return "DEFER_WIND"

    if in_drydown_lockout:
        return "LOCKOUT"

    if moisture is None:
        return "WATER"  # stale/unavailable sensor → fallback watering

    if moisture > refill_point:
        return "SKIP"

    # At or below the refill point — this zone is due a soak.
    if forecast_precip_in >= 0.15:
        return "SKIP"  # meaningful rain coming; let it do the work

    return "WATER"


def soak_plan(total_minutes: int, cycles: int, min_cycle_minutes: int) -> list[int]:
    """
    Split a run into soak cycles, returning per-cycle minutes.

    Two things the pre-0.8.0 implementation got wrong: it used integer floor
    division and silently dropped the remainder (5 min over 4 cycles became
    4 x 1 min, so a fifth of the water vanished), and it applied cycling to
    runs far too short to need it. Cycling exists to prevent runoff on a run
    long enough to cause runoff; one-minute pulses just wet the canopy and
    evaporate.
    """
    total = max(0, int(total_minutes))
    if total == 0:
        return []
    cycles = max(1, int(cycles))
    if cycles == 1 or total // cycles < min_cycle_minutes:
        return [total]
    base, extra = divmod(total, cycles)
    return [base + (1 if i < extra else 0) for i in range(cycles)]


def calibrated_duration(
    current_moisture: float,
    target_moisture: float,
    cal_rate: float | None,
    fallback_minutes: int,
    max_minutes: int,
) -> int:
    """Return watering duration in minutes.

    target_moisture is the zone's fill target (roughly field capacity), not a
    few points above the trigger. Under the interval-adaptive model the deficit
    is large by design, so max_minutes is usually what governs — set it to a
    real deep-soak length rather than the old top-up length.
    """
    if cal_rate is None or cal_rate <= 0:
        return fallback_minutes
    needed = target_moisture - current_moisture
    if needed <= 0:
        return fallback_minutes
    return min(int(math.ceil(needed / cal_rate)), max_minutes)


def update_calibration(
    previous: float | None,
    rise: float,
    duration_minutes: int,
    min_run_minutes: int,
    down_weight: float,
    min_rate: float,
    max_rate: float,
) -> tuple[float | None, str]:
    """Fold one observed soil response into the calibration estimate.

    Returns (new_rate, reason). new_rate is None when the sample is rejected.

    The pre-0.8.0 version discarded every non-positive rise, so an over-reading
    stuck permanently while an honest non-response taught nothing — the
    estimate could only ratchet upward. A run of meaningful length that fails
    to move the probe is the strongest evidence the rate is too high, so it now
    revises downward instead of being thrown away.
    """
    if duration_minutes < min_run_minutes:
        return None, f"run too short to learn from ({duration_minutes} min)"

    if rise <= 0:
        # Genuine non-response: the current estimate is over-optimistic.
        if previous is None:
            return None, "no prior estimate and no measurable rise"
        revised = max(min_rate, round(previous * (1 - down_weight), 4))
        return revised, f"no rise over {duration_minutes} min — revised down"

    observed = rise / duration_minutes
    if previous is None:
        new = observed
    else:
        new = 0.8 * previous + 0.2 * observed
    new = max(min_rate, min(max_rate, round(new, 4)))
    return new, f"rise {rise:+.1f}% over {duration_minutes} min"


def should_cool(
    soil_temp: float | None,
    threshold: float,
    temp_rise_rate: float | None,
    rise_min_rate: float,
    moisture: float | None,
    moisture_ceiling: float,
    wind_mph: float,
    wind_limit: float,
    precip_in: float,
    runs_today: int,
    max_runs: int,
    minutes_since_cooling: float | None,
    min_interval: float,
    minutes_since_watering: float | None,
    post_water_lockout: float,
) -> tuple[bool, str]:
    """Decide whether to syringe a zone to cool its root zone.

    Returns (run, reason). Cooling is a heat-stress intervention, not
    irrigation: a short application to take the top off a temperature spike.
    The caller must not let it touch last_watered, the calibration loop, or the
    dry-down interval.

    Triggering on measured root-zone temperature and rise rate — rather than a
    fixed clock — lets each zone self-time. A zone that peaks at midday arms in
    the late morning; a west exposure that peaks late afternoon arms then, with
    no per-zone schedule to maintain and no drift as the sun angle changes.
    """
    if soil_temp is None:
        return False, "no soil temperature reading"
    if soil_temp < threshold:
        return False, f"root zone {soil_temp:.0f}°F below {threshold:.0f}°F"
    if temp_rise_rate is None:
        return False, "no temperature trend yet"
    if temp_rise_rate < rise_min_rate:
        return False, f"root zone {soil_temp:.0f}°F but no longer rising"
    if runs_today >= max_runs:
        return False, f"daily cooling limit reached ({runs_today}/{max_runs})"
    if minutes_since_cooling is not None and minutes_since_cooling < min_interval:
        return False, f"cooled {int(minutes_since_cooling)} min ago"
    if minutes_since_watering is not None and minutes_since_watering < post_water_lockout:
        return False, f"watered {int(minutes_since_watering)} min ago — already wet"
    if moisture is not None and moisture >= moisture_ceiling:
        return False, f"soil already at {moisture:.0f}%"
    if wind_mph > wind_limit:
        return False, f"wind {wind_mph:.0f} mph — spray would blow away"
    if precip_in >= 0.15:
        return False, f"{precip_in:.2f} in rain forecast"
    return True, f"root zone {soil_temp:.0f}°F and rising {temp_rise_rate * 60:.1f}°F/h"
