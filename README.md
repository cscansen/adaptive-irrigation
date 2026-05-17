# Adaptive Irrigation

A Home Assistant custom integration that makes soil-moisture-aware, weather-informed watering decisions. Replaces hardcoded JSON automations with a self-calibrating decision engine.

## Features

- **Per-zone config entries** — add each irrigation zone independently via the HA UI
- **Soil moisture trend** — computes %/hour drying rate from HA recorder history (no external database)
- **ET-based weather logic** — Hargreaves-Samani reference ET from HA weather forecast; skips watering when rain is forecast
- **Motion deferral** — skips zones with active motion sensors, retries next poll
- **Wind skip** — defers when wind exceeds 25 mph
- **Self-calibration** — measures actual moisture rise per minute after each watering; improves duration estimates over time
- **Persistent notifications** — per-zone dashboard cards for every watering decision
- **Manual override services** — `water_zone` and `evaluate_now`
- **Sensor-free mode** — drip zones with no soil sensor infer drying rate from peer zones' moisture trends; falls back to a configurable day interval

## Installation

1. In HA: HACS → Integrations → ⋮ → Custom repositories
2. URL: `https://github.com/cscansen/adaptive-irrigation` — Category: Integration → Add
3. Search "Adaptive Irrigation" → Download
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → "Adaptive Irrigation"

## Zone Configuration

| Field | Description | Default |
|-------|-------------|---------|
| Zone name | Unique identifier (e.g. `east`) | — |
| Zone type | `Summer` — threshold-based, any time. `Seedling` — 4×/day windows (06:00, 10:00, 14:00, 18:00), 93% threshold | Summer |
| Valve switch | `switch.yardian_controller_*` entity | — |
| Soil sensors | One or more `sensor.*` entities (averaged) | — |
| Motion sensor | Optional `binary_sensor.*` to defer watering | — |
| Soil threshold | Water when soil drops below this % | 92% |
| Max duration | Hard cap on watering time | 20 min |
| Fallback duration | Used when sensor is stale or no calibration data | 6 min |
| Crop coefficient (Kc) | Scales reference ET for zone type | 0.8 (lawn) |
| Sensor required | Disable for drip zones with no soil sensor | on |
| Water interval days | Sensor-free zones: base days between waterings; also early-waters if peers are drying > 0.3%/h and half the interval has passed | 3 |
| Min interval | Prevent re-watering within this window | 45 min |

## Entities (per zone)

| Entity | Description |
|--------|-------------|
| `sensor.*_moisture` | Current avg soil % |
| `sensor.*_moisture_trend` | Drying rate in %/hour |
| `sensor.*_et_today` | Reference ET × Kc in mm/day |
| `sensor.*_status` | Human-readable last decision |
| `sensor.*_last_watered` | Timestamp of last watering |
| `sensor.*_calibration_rate` | Measured moisture rise %/min |
| `switch.*_auto_watering` | Enable/disable automatic watering |

## Services

### `adaptive_irrigation.water_zone`
Manually water a zone for a given duration.
```yaml
service: adaptive_irrigation.water_zone
data:
  zone_id: east
  duration_minutes: 10
```

### `adaptive_irrigation.evaluate_now`
Force an immediate watering evaluation outside the 15-minute poll cycle.
```yaml
service: adaptive_irrigation.evaluate_now
data:
  zone_id: east
```

## Decision Logic

Each poll cycle (every 15 min) per zone:

1. Auto watering switch off → skip
2. Watered within `min_interval` OR valve ran recently (any source) OR valve currently ON → skip
3. **Seedling zones only**: outside a 06:00 / 10:00 / 14:00 / 18:00 (±30 min) window → skip
4. Motion detected → defer (notify)
5. Wind > 25 mph → defer (notify)

**Zones with soil sensors:**

6. Rain forecast ≥ 0.15 in AND soil > 85% → skip
7. Soil < threshold → **water**
8. Soil ≥ threshold AND drying faster than 0.5%/hr AND < 3h until threshold−5% → **water** (pre-emptive)
9. Otherwise → skip

Duration = `(target - current) / calibration_rate`, capped at max_duration. Falls back to fallback_duration until calibration exists.

**Sensor-free zones (drip/trees):**

6. Rain forecast ≥ 0.15 in → skip
7. Peer zones drying faster than −0.3%/hr AND ≥ half of `water_interval_days` elapsed → **water** (early)
8. `water_interval_days` elapsed → **water**
9. Otherwise → skip

Duration = `fallback_duration` (fixed; no calibration without a sensor).

## Setting Thresholds

The right threshold depends entirely on what you're growing, not just the sensor's output range. Some starting points:

| Situation | Suggested threshold |
|-----------|-------------------|
| Baby grass / germination | 93–95% — seeds need to stay consistently wet |
| Established lawn | 88–92% — some drying between cycles is fine |
| Shrubs / trees (drip) | 75–85% — deeper roots tolerate more variation |
| Vegetable garden | 90–93% — depends on crop and growth stage |

If the zone is skipping when the soil feels dry, raise the threshold. If it's watering too frequently, lower it. The calibration sensor shows how much each minute of watering actually moves the needle, which helps set max and fallback durations.

## Running Alongside Existing Automations

The integration is safe to run in parallel with existing automations during a pilot. Two guards prevent double-watering:

1. **Internal guard** — skips if the integration itself watered within `min_interval` minutes
2. **Valve guard** — checks the valve switch's `last_changed` timestamp; skips if the valve was run by *any* source (including other automations) within `min_interval` minutes; also skips if the valve is currently ON

Recommended pilot sequence: enable east zone, observe for 2 weeks, then expand one zone at a time and disable the corresponding legacy automation actions.
