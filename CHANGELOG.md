# Changelog

## [0.6.1] - 2026-05-17

### Added
- **Weather entity config** — first-zone setup now includes a "Weather Source" step where you pick the weather entity (e.g. `weather.home`). Validates the entity exists before allowing you to proceed; shows a clear error if no weather integration is configured. Subsequent zones inherit the selection automatically — you only pick it once.
- `strings.json` — proper UI labels and error messages for all config/options flow steps

### Fixed
- OptionsFlow changes were silently ignored: coordinator read `entry.data` but OptionsFlow writes to `entry.options`. Coordinator now merges both (`{**entry.data, **entry.options}`) so reconfiguring a zone actually takes effect on the next poll.
- Weather entity is now read from `hass.data[DOMAIN]["weather_entity"]` (set at zone load time) rather than hardcoded to `weather.home`.
- OptionsFlow for the primary zone (the one that set the weather entity) shows the weather field so you can change it later without removing and re-adding the zone.

## [0.6.0] - 2026-05-17

### Added
- **Rain Forecast sensor** per zone (`sensor.*_rain_forecast`) — inches of precipitation in today's forecast; now visible on dashboard and always available regardless of whether rain actually causes a skip
- **Wind Forecast sensor** per zone (`sensor.*_wind_forecast`) — mph from today's forecast

### Changed
- Status messages now include weather and soil context for every decision:
  - Watering: `Watering — 8 min (soil 88%, trend −0.6%/h)`
  - Soil skip: `Skipped — soil 97% ≥ 92%, 0.20 in rain`
  - Rain+soil skip: `Skipped — 0.25 in rain forecast, soil 91%`
  - Rain skip (sensor-free): `Skipped — 0.25 in rain forecast`
  - Wind defer: unchanged (already showed mph)
- Dashboard rebuilt: one compact entities card per zone replaces the previous cluttered glance/stack layout

## [0.5.2] - 2026-05-17

### Fixed
- `KeyError: 'adaptive_irrigation'` crash on startup: coordinator's first refresh fires before `hass.data[DOMAIN]` is populated, so the new master-switch check blew up. Changed to `hass.data.get(DOMAIN, {}).get("master_enabled", True)`.

## [0.5.1] - 2026-05-17

### Fixed
- False "valve ran X min ago" status on HA restart: Yardian switches publish an `unavailable → off` state transition at startup which updated `last_changed` even though no valve actually ran. Guard now only applies when the valve was observed in the `on` state during the current HA session; a stale `last_changed` from startup is ignored.

## [0.5.0] - 2026-05-17

### Added
- **Master switch** (`switch.adaptive_irrigation`) — integration-level pause; blocks all zones without touching per-zone auto-watering switches. Persists across restarts. Lives on a shared "Adaptive Irrigation" device.
- **Seedling Mode switch** per zone (`switch.*_seedling_mode`) — toggle seedling/germination mode live from the dashboard without re-entering config flow. Default state is inferred from zone type at setup; persists across restarts.
- **Soil Threshold slider** per zone (`number.*_soil_threshold`) — live-adjust the moisture % below which watering triggers. Range 60–99%, step 1%. Defaults to configured value; persists across restarts.
- **Water Interval slider** per zone (`number.*_water_interval_days`) — live-adjust drip zone base watering interval. Range 1–14 days, step 1. Only meaningful for sensor-free zones. Persists across restarts.
- **Max Duration slider** per zone (`number.*_max_duration`) — live cap on watering time. Range 1–60 min, step 1. Persists across restarts.
- All live-tunable values fall back to the zone's config-flow setting when not yet restored.

## [0.4.1] - 2026-05-17

### Fixed
- Spurious "zone ran" notification on HA restart: `async_config_entry_first_refresh` fires before entity restore completes, so `last_watered` was always `None` on the first poll — bypassing the startup guard and potentially triggering a false watering decision. First poll now skips all watering decisions and returns `Idle`; entities restore before the second poll 15 min later.

## [0.4.0] - 2026-05-17

### Added
- **Peer trend inference** for sensor-free zones (drip/trees): averages moisture trend from zones that have real soil sensors to infer yard drying rate
- Sensor-free zones now use a proper decision path (`_decide_sensor_free`) instead of watering unconditionally every poll — fixes a bug where drip zones would have tried to water every 15 minutes
- `water_interval_days` config field: base interval between waterings for sensor-free zones (default 3 days); also acts as fallback floor when no peer trend is available
- Early watering when peers are drying faster than −0.3%/hr and at least half the interval has passed
- Status sensor shows days remaining until next watering and current peer trend for sensor-free zones
- Sprinkler icon (`icon.png`) added to integration

### Fixed
- `logic.decide()` no longer has a dead `sensor_required=False → WATER` branch; sensor-free logic fully moved to coordinator

## [0.3.1] - 2026-05-17

### Fixed
- Motion sensor field is now truly optional — no default entity required, zones without a motion sensor can be configured without errors

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
