# Changelog

## [0.3.0] - 2026-05-17

### Added
- **Zone Type** field in config flow: `Summer` (default) or `Seedling / Germination`
- Seedling mode gates watering to 4 daily windows: 06:00, 10:00, 14:00, 18:00 (±30 min each)
- Seedling mode defaults to 93% soil threshold and 4 min fallback duration
- Status sensor shows next window time when outside seedling windows
- Threshold and fallback duration fields now default based on selected zone type

## [0.2.1] - 2026-05-17

### Fixed
- Double-watering guard now checks the valve switch's own `last_changed` timestamp, catching waterings triggered by any source (e.g. existing automations running in parallel during pilot). Previously only tracked waterings initiated by the integration itself. Also blocks evaluation when the valve is currently ON.

## [0.2.0] - 2026-05-17

### Added
- Full watering decision engine in coordinator (WATER / SKIP / DEFER_WIND / DEFER_MOTION / MONITOR)
- Valve control: opens/closes `CONF_VALVE_SWITCH` via `switch.turn_on/off` service
- Weather integration: fetches daily forecast via `weather.get_forecasts` service
- ET calculation: Hargreaves-Samani reference ET × crop coefficient (Kc)
- Rain skip: defers when forecast precipitation ≥ 0.15 in and soil > 85%
- Wind skip: defers when wind > 25 mph
- Motion deferral: skips zone when motion sensor is active
- Self-calibration: measures moisture rise/min 30 min after each watering via `async_call_later`
- Startup guard: skips watering if zone was watered within `min_interval` minutes
- Persistent notifications per zone for every decision (overwrites on each poll)
- `water_zone` service: manually water a zone for a specified duration
- `evaluate_now` service: force immediate evaluation outside 15-min cycle
- ET Today sensor (`sensor.*_et_today`) populated from weather forecast
- Status sensor now reflects real decision outcomes
- Switch + calibration + last_watered values restored across HA restarts and synced to coordinator

### Changed
- Manifest version bumped to 0.2.0
- Coordinator data dict now includes `last_watered`, `calibration`, `et_today`, `status`
- Sensor entities read all values from coordinator data (single source of truth)

## [0.1.0] - 2026-05-17

### Added
- Initial integration skeleton
- ConfigEntry per zone with config flow UI
- DataUpdateCoordinator polling every 15 minutes
- Soil moisture reading (averaged across multiple sensors, stale detection)
- Moisture trend via HA recorder history (linear regression over 6h)
- RestoreEntity sensors: last_watered, calibration_rate
- Auto Watering switch (RestoreEntity, persists across restarts)
- HACS manifest (`hacs.json`)
- Services declaration (`services.yaml`)
