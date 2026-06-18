# Changelog

## [0.7.2] - 2026-06-18

### Changed
- **Recency guard now waits for a sensor poll, not a fixed timer** — after a zone
  waters, re-evaluation is blocked until at least one soil sensor reports a reading
  with a timestamp after the valve closed, rather than waiting a fixed `min_interval`
  minutes. This means the zone can re-water in the same morning window if soil is
  still below threshold after the next 15-minute sensor poll — important after
  skipped days when the yard needs multiple runs to recover. Sensor-free zones fall
  back to a flat 15-minute wait (one poll cycle). Status during the wait reads
  `Idle — waiting for sensor poll after watering (N min ago)`.
- **Dashboard: Evaluate Now buttons added** — a 2-column grid card sits below the
  System card with per-zone Evaluate Now buttons and a Calibration Status button,
  matching the HVAC dashboard pattern.

## [0.7.1] - 2026-06-18

### Fixed
- **Valve unavailability now blocks watering** — if the Yardian zone switch is
  `unavailable` (controller offline, integration not loaded), the coordinator skips
  the watering decision and reports `Skipped — valve unavailable (Yardian offline?)`
  instead of silently calling `switch.turn_on` on an unavailable entity and claiming
  "Watering" while the sprinklers do nothing. A secondary guard in `_water_zone`
  catches the same condition right before the valve open call.

## [0.7.0] - 2026-06-17

### Fixed
- **Calibration rate now persists across HA restarts** — calibration is written to
  HA storage (`Store`) after every successful update. On startup, the stored value
  is loaded before the first poll cycle, so the coordinator always has the correct
  rate immediately. Previously, calibration lived only in `RestoreEntity` state, which
  requires the entity to have shown a non-unknown value at shutdown — a race that was
  consistently lost.
- **Calibration rate now reflects immediately in HA** — `_calibration_followup` now
  updates `coordinator.data["calibration"]` directly so the entity value updates on
  the next `async_update_listeners()` call rather than waiting up to 15 minutes for
  the next poll cycle.
- **Fast-draining soil zones can now calibrate** — the `rise <= 0` guard that
  silently skipped calibration has been tightened to `rise < -1.0`. Zones like Yard
  West where surface evaporation in heat/wind causes the sensor to read slightly below
  the pre-watering baseline will now accumulate calibration data instead of being
  permanently skipped.

### Added
- **`adaptive_irrigation.calibration_status` service** — posts a persistent
  notification with a full debug dump for all zones: calibration rate, data source
  (Store vs RestoreEntity), current soil moisture, last watering context, and a
  projected rate if the followup were to run right now.
- **`adaptive_irrigation.force_calibration` service** — manually triggers the
  calibration followup for a zone using the current soil reading. Use this immediately
  after a manual watering run to verify the sensor detects moisture rise and to seed
  calibration data without waiting for the next automatic cycle.

## [0.6.9] - 2026-05-17

### Added
- **Seedling Expires date picker** per zone (`datetime.*_seedling_expires`) — auto-set to 30 days from now when seedling mode is turned on; editable from the dashboard. When the expiry date passes, seedling mode is automatically turned off and a dashboard notification is posted.
- **Seedling Threshold slider** added to the irrigation dashboard below the Seedling Mode toggle for each zone.
- **Seedling Expires date picker** added to the irrigation dashboard below the Seedling Threshold slider for each zone.

## [0.6.8] - 2026-05-17

### Changed
- **Seedling mode simplified** — seedling mode no longer gates watering to 4 fixed daily windows. All zones (seedling or not) now use the same configurable watering window. When seedling mode is on, the zone uses the **Seedling Threshold** slider instead of the normal threshold, keeping soil wetter for germination.
- **Seedling Threshold slider** added per zone (`number.*_seedling_threshold`) — the moisture % below which a seedling-mode zone waters. Range 10–99%, default 35%.
- **Soil Threshold slider minimum** lowered from 60% to 10% to match actual sensor range.
- **Default thresholds updated** — normal: 92% → 25%, seedling: 93% → 35%, reflecting accurate sensor calibration.

## [0.6.7] - 2026-05-17

### Fixed
- **Moisture shows unknown on restart** — coordinator now seeds moisture from the recorder (most recent value within 8 h) when soil sensor entities haven't finished loading yet at HA startup. Once a live reading comes in, the cached value takes over. All four active zones now show real moisture readings immediately on restart.

## [0.6.6] - 2026-05-17

### Fixed
- **Last Watered shows unknown on restart** — coordinator now queries the valve switch's recorder history (up to 30 days) on first poll and seeds `last_watered` from the last on→off transition. Existing installs will show real data immediately after the next HA restart instead of "unknown" until the integration itself waters a zone.

### Changed
- **Irrigation dashboard** — added shared System card (System Active, Water Restriction, Window Start/End, Daily Budget, Daily Used) and Weather card (Weather Source, Rain Forecast, Wind Forecast, ET Today). ET Today, Rain Forecast, and Wind Forecast removed from individual zone cards.

## [0.6.5] - 2026-05-17

### Changed
- **Dedicated Configuration entry** — System settings now live in their own "Configuration" config entry (separate from any zone). It appears as its own item in Settings → Integrations with a dedicated Configure button. First time adding the integration creates this entry; subsequent "Add Integration" clicks add zones.
- **Configuration is now editable** — The Configuration entry's options flow lets you change weather entity, watering window, water meter, and daily budget independently of any zone.
- **Watering window shows as times** — Window Start and Window End are now dropdown selects showing "5:00 AM" / "10:00 AM" style labels instead of the confusing "5 hr" / "10 hr" number sliders.
- Config entry migration (v1 → v2) tags all existing zone entries automatically on startup.

## [0.6.4] - 2026-05-17

### Changed
- **Configuration device** — all system-level controls now live on a dedicated `Configuration` device instead of being scattered under zone devices. The device contains: Weather Source (sensor), Watering Window Start/End (numbers), Daily Water Budget (number), Daily Water Used (sensor), System Active (switch), Water Restriction (switch).
- **Watering window is now system-wide** — Window Start and Window End moved from per-zone number entities to the Configuration device. One window applies to all zones. Existing window settings restore from HA state automatically.
- **Weather Source sensor** added to Configuration device — shows which weather entity the integration is currently reading from.

## [0.6.3] - 2026-05-17

### Added
- **Water Restriction switch** (`switch.adaptive_irrigation_water_restriction`, system device) — when on, all zones are blocked from watering and report `Paused — water restriction active`. For drought orders or HOA restrictions. State persists across restarts.
- **Daily Water Budget** (`number.adaptive_irrigation_daily_budget`, system device) — set a daily gallon cap for the whole system. Zones are gated before each session; if the budget is exhausted the zone reports `Skipped — budget exhausted (X/Y gal)`. Duration is truncated if the remaining budget only allows a shorter run. Set to 0 for unlimited (default).
- **Daily Water Used sensor** (`sensor.adaptive_irrigation_daily_used`, system device) — shows today's total water use. Reads live from a Flume (or any cumulative `sensor.*`) water meter if configured; otherwise accumulates `duration × flow rate` estimates. Resets at midnight local time.
- **Flow Rate number** (`number.*_flow_rate`) per zone — gallons per minute for the valve (0.5–20, default 2.0). Used to convert runtime to volume for budget tracking.
- **Water meter entity** and **daily budget** are now configurable in the system setup step and options flow for the primary zone entry. Flume or any cumulative sensor entity can be selected.

### Fixed
- Master switch label: `"Adaptive Irrigation"` → `"System Active"` so `on = running` is unambiguous on dashboard cards.

## [0.6.2] - 2026-05-17

### Added
- **Per-zone watering window** — two new number entities per zone: `Watering Window Start` (default 5am) and `Watering Window End` (default 10am). Summer mode polls are gated to this window; outside it the status reads `Idle — outside watering window (05:00–10:00)`. Seedling mode is unaffected (it uses its own 4-window schedule). Adjustable per zone from the dashboard without touching config.

### Fixed
- **Sensor staleness threshold** raised from 4 h → 8 h (`STALE_SENSOR_HOURS`). Sensors that last reported at ~11 pm were being treated as stale at 5:30 am and triggering unnecessary fallback waterings.

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
