DOMAIN = "adaptive_irrigation"

CONF_WEATHER_ENTITY = "weather_entity"
DEFAULT_WEATHER_ENTITY = "weather.home"

CONF_ZONE_NAME = "zone_name"
CONF_ZONE_TYPE = "zone_type"
CONF_VALVE_SWITCH = "valve_switch"
CONF_SOIL_SENSORS = "soil_sensors"
CONF_MOTION_SENSOR = "motion_sensor"
CONF_SOIL_THRESHOLD = "soil_threshold"
CONF_MAX_DURATION = "max_duration"
CONF_FALLBACK_DURATION = "fallback_duration"
CONF_CROP_COEFFICIENT = "crop_coefficient"
CONF_SENSOR_REQUIRED = "sensor_required"
CONF_MIN_INTERVAL = "min_interval"
CONF_WATER_INTERVAL_DAYS = "water_interval_days"
CONF_WINDOW_START_HOUR = "window_start_hour"
CONF_WINDOW_END_HOUR = "window_end_hour"
CONF_WATER_METER_ENTITY = "water_meter_entity"
CONF_DAILY_BUDGET_GALLONS = "daily_budget_gallons"
CONF_FLOW_RATE_GPM = "flow_rate_gpm"

ZONE_TYPE_SUMMER = "summer"
ZONE_TYPE_SEEDLING = "seedling"
DEFAULT_ZONE_TYPE = ZONE_TYPE_SUMMER

SEEDLING_DEFAULT_THRESHOLD = 35
SEEDLING_DEFAULT_FALLBACK = 4

DEFAULT_WATER_INTERVAL_DAYS = 3
DEFAULT_WINDOW_START_HOUR = 5
DEFAULT_WINDOW_END_HOUR = 10
DEFAULT_FLOW_RATE_GPM = 2.0
DEFAULT_DAILY_BUDGET_GALLONS = 0.0
PEER_TREND_DRYING_THRESHOLD = -0.3  # %/hr — peers drying this fast triggers early watering

DEFAULT_SOIL_THRESHOLD = 25
DEFAULT_MAX_DURATION = 20
DEFAULT_FALLBACK_DURATION = 6
DEFAULT_MIN_INTERVAL = 45
DEFAULT_CROP_COEFFICIENT = "0.8"

CONF_SOAK_CYCLES = "soak_cycles"
CONF_SOAK_PAUSE_MINUTES = "soak_pause_minutes"
DEFAULT_SOAK_CYCLES = 1
DEFAULT_SOAK_PAUSE_MINUTES = 30

# Below this many minutes per cycle, splitting a run into soak cycles delivers
# pulses too short to infiltrate. Collapse to a single run instead.
MIN_CYCLE_MINUTES = 5

# --- Interval-adaptive model (v0.8.0) ---
# Deep-and-infrequent: let the zone dry to refill_point, then soak back to
# fill_target. Replaces the old "top up to threshold + 5" behaviour, which
# watered little and often and trained roots to stay at the surface.
CONF_REFILL_POINT = "refill_point"
CONF_FILL_TARGET = "fill_target"
DEFAULT_REFILL_POINT = 40.0
DEFAULT_FILL_TARGET = 70.0

# After a soak, suppress moisture-driven re-evaluation for this long. The probes
# take ~4 h to finish responding to an application, so anything sooner is acting
# on a reading that hasn't caught up yet.
DRYDOWN_LOCKOUT_HOURS = 18

# --- Calibration (v0.8.0) ---
# Old behaviour sampled once at +30 min, which captured under half the eventual
# rise, and discarded every non-positive result — so the estimate could only
# ratchet upward. Now: follow the probe to its peak, and let a genuine
# non-response revise the rate down.
CALIBRATION_PEAK_TIMEOUT_HOURS = 8
# The probe can sit flat for well over an hour mid-climb (observed: 110 min at
# 43% before continuing to 50%), so the peak is confirmed by elapsed time
# without a new maximum, not by a count of consecutive equal readings.
CALIBRATION_SETTLE_MINUTES = 90
CALIBRATION_MIN_RUN_MINUTES = 5       # shorter runs teach nothing; don't learn
CALIBRATION_DOWN_WEIGHT = 0.3         # EWMA weight when revising downward
CALIBRATION_MIN_RATE = 0.05
CALIBRATION_MAX_RATE = 2.0

# --- Soil temperature + cooling (v0.8.0) ---
CONF_SOIL_TEMP_SENSOR = "soil_temp_sensor"
CONF_COOLING_ENABLED = "cooling_enabled"
CONF_COOLING_TEMP_THRESHOLD = "cooling_temp_threshold"
CONF_COOLING_DURATION = "cooling_duration_minutes"
CONF_COOLING_MOISTURE_CEILING = "cooling_moisture_ceiling"

CONF_COOLING_WINDOW_START_HOUR = "cooling_window_start_hour"
CONF_COOLING_WINDOW_END_HOUR = "cooling_window_end_hour"
CONF_COOLING_MAX_RUNS_PER_DAY = "cooling_max_runs_per_day"
CONF_COOLING_MIN_INTERVAL = "cooling_min_interval_minutes"
CONF_COOLING_WIND_LIMIT = "cooling_wind_limit_mph"

DEFAULT_COOLING_ENABLED = True
DEFAULT_COOLING_TEMP_THRESHOLD = 95.0
DEFAULT_COOLING_DURATION = 3
DEFAULT_COOLING_MOISTURE_CEILING = 80.0
DEFAULT_COOLING_WINDOW_START_HOUR = 11
DEFAULT_COOLING_WINDOW_END_HOUR = 18
DEFAULT_COOLING_MAX_RUNS_PER_DAY = 3
DEFAULT_COOLING_MIN_INTERVAL = 60
DEFAULT_COOLING_WIND_LIMIT = 15.0

# Never syringe past this hour regardless of configuration — a canopy left wet
# overnight invites fungal disease. Enforced in code, not left to config.
COOLING_HARD_STOP_HOUR = 18

# Cooling arms only while the root zone is still heating. A zone already past
# its thermal peak is coasting down on its own.
COOLING_TREND_MINUTES = 20
COOLING_RISE_MIN_RATE = 0.05          # °F/min

# Don't syringe a zone that was irrigated recently — it's already wet and cool.
COOLING_POST_WATER_LOCKOUT_MINUTES = 180

# --- Root training (v0.8.0: measurement only) ---
# Dry-down duration per cycle is recorded so the deferred auto-tuner has real
# data to work from. Deliberate depletion is a spring/autumn technique and must
# never run while the root zone is hot — roots die back above ~85 °F.
ROOT_TRAINING_MAX_SOIL_TEMP = 80.0

CROP_COEFFICIENTS = {
    "lawn": 0.8,
    "mixed": 0.9,
    "garden": 1.0,
    "drip": 0.6,
}

SCAN_INTERVAL_MINUTES = 15
TREND_HOURS = 6
CALIBRATION_FOLLOWUP_SECONDS = 1800
STALE_SENSOR_HOURS = 8

ENTRY_TYPE_SYSTEM = "system"
ENTRY_TYPE_ZONE   = "zone"

HOUR_LABELS = [
    "12:00 AM", "1:00 AM",  "2:00 AM",  "3:00 AM",  "4:00 AM",  "5:00 AM",
    "6:00 AM",  "7:00 AM",  "8:00 AM",  "9:00 AM",  "10:00 AM", "11:00 AM",
    "12:00 PM", "1:00 PM",  "2:00 PM",  "3:00 PM",  "4:00 PM",  "5:00 PM",
    "6:00 PM",  "7:00 PM",  "8:00 PM",  "9:00 PM",  "10:00 PM", "11:00 PM",
]
