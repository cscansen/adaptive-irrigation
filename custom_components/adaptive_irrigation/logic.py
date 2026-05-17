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
    threshold: float,
    trend: float | None,
    forecast_precip_in: float,
    wind_mph: float,
    sensor_required: bool,
) -> str:
    """
    Return one of: WATER, SKIP, DEFER_WIND, MONITOR.
    Only called for zones with soil sensors (sensor_required=True).
    Sensor-free zones are handled by coordinator._decide_sensor_free().
    Motion check is handled by the coordinator before calling this function.
    """
    if wind_mph > 25:
        return "DEFER_WIND"

    if moisture is None:
        return "WATER"  # stale/unavailable sensor → fallback watering

    if forecast_precip_in >= 0.15 and moisture > 85:
        return "SKIP"

    if moisture < threshold:
        return "WATER"

    if trend is not None and trend < -0.5:
        # Drying fast — estimate hours to threshold-5%
        hours_to_dry = (moisture - (threshold - 5)) / abs(trend)
        if hours_to_dry < 3:
            return "MONITOR"  # pre-emptive: water now

    return "SKIP"


def calibrated_duration(
    current_moisture: float,
    target_moisture: float,
    cal_rate: float | None,
    fallback_minutes: int,
    max_minutes: int,
) -> int:
    """Return watering duration in minutes."""
    if cal_rate is None or cal_rate <= 0:
        return fallback_minutes
    needed = target_moisture - current_moisture
    if needed <= 0:
        return fallback_minutes
    return min(int(math.ceil(needed / cal_rate)), max_minutes)
