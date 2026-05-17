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

ZONE_TYPE_SUMMER = "summer"
ZONE_TYPE_SEEDLING = "seedling"
DEFAULT_ZONE_TYPE = ZONE_TYPE_SUMMER

# Seedling mode: 4 watering windows per day (start_min, end_min) in local time
SEEDLING_WINDOWS = [(6 * 60, 6 * 60 + 30), (10 * 60, 10 * 60 + 30), (14 * 60, 14 * 60 + 30), (18 * 60, 18 * 60 + 30)]
SEEDLING_DEFAULT_THRESHOLD = 93
SEEDLING_DEFAULT_FALLBACK = 4

DEFAULT_WATER_INTERVAL_DAYS = 3
DEFAULT_WINDOW_START_HOUR = 5
DEFAULT_WINDOW_END_HOUR = 10
PEER_TREND_DRYING_THRESHOLD = -0.3  # %/hr — peers drying this fast triggers early watering

DEFAULT_SOIL_THRESHOLD = 92
DEFAULT_MAX_DURATION = 20
DEFAULT_FALLBACK_DURATION = 6
DEFAULT_MIN_INTERVAL = 45
DEFAULT_CROP_COEFFICIENT = "0.8"

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
