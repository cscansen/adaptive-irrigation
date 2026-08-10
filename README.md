# Adaptive Irrigation

A Home Assistant custom integration that makes soil-moisture-aware, weather-informed watering decisions, and manages heat-stress cooling from measured root-zone temperature. Replaces hardcoded JSON automations with a self-calibrating decision engine.

**Watering is deep and infrequent by design.** A zone is left alone until it dries to its *refill point*, then soaked back toward field capacity. The dry-down between soaks is deliberate — it is what drives roots downward. Topping up little and often keeps roots at the surface.

## Features

- **Per-zone config entries** — add each irrigation zone independently via the HA UI
- **Soil moisture trend** — computes %/hour drying rate from HA recorder history (no external database)
- **ET-based weather logic** — Hargreaves-Samani reference ET from HA weather forecast; skips watering when rain is forecast
- **Motion deferral** — skips zones with active motion sensors, retries next poll
- **Wind skip** — defers when wind exceeds 25 mph
- **Heat-stress cooling** — per-zone syringing triggered on measured root-zone temperature while it is still rising, so each zone self-times to its own thermal peak; every run is scored for the temperature drop it actually achieved
- **Self-calibration** — follows the probe to its peak after a soak (not a fixed sample) and revises downward when a run fails to move it
- **Foreign-run detection** — notices watering started by anything else sharing the valves and discards the contaminated measurement
- **Soak/cycle watering** — splits a long run into cycles with soak pauses to prevent runoff; runs too short to need cycling stay continuous
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
| Min interval | *(removed — replaced by sensor-poll guard)* | — |

## Entities

### Integration-level

| Entity | Description |
|--------|-------------|
| `switch.adaptive_irrigation` | Master pause — disables all zones, watering and cooling alike |
| `switch.adaptive_irrigation_water_restriction` | Blocks all water use including cooling |
| `sensor.adaptive_irrigation_daily_water_used` | Daily total (whole-house if a meter entity is set) |

### Per zone

| Entity | Description |
|--------|-------------|
| `sensor.*_moisture` | Current avg soil % |
| `sensor.*_moisture_trend` | Drying rate in %/hour |
| `sensor.*_et_today` | Reference ET × Kc in mm/day |
| `sensor.*_status` | Human-readable last decision |
| `sensor.*_last_watered` | Timestamp of last watering |
| `sensor.*_calibration_rate` | Measured moisture rise %/min |
| `sensor.*_days_to_refill` | Projected days until the next soak falls due |
| `sensor.*_soil_temp` | Root-zone temperature (attributes: rise rate, cooling status) |
| `sensor.*_cooling_runs_today` | Cooling applications so far today |
| `sensor.*_cooling_delta` | °F change achieved by the last cooling run |
| `sensor.*_last_cooling` | Timestamp of last cooling run |
| `switch.*_auto_watering` | Enable/disable automatic watering for this zone |
| `switch.*_cooling_enabled` | Enable/disable heat-stress cooling for this zone |
| `switch.*_seedling_mode` | Toggle seedling/germination watering windows live |
| `number.*_refill_point` | Dry to here before the next soak (10–90%) |
| `number.*_fill_target` | Soak up to roughly field capacity (20–99%) |
| `number.*_fallback_duration` | Soak length when no calibration exists (1–90 min) |
| `number.*_cooling_threshold` | Root-zone °F at which cooling arms (80–120) |
| `number.*_cooling_duration` | Length of a cooling application (1–10 min) |
| `number.*_soil_threshold` | Legacy threshold — used by seedling mode only |
| `number.*_water_interval_days` | Drip zone base interval between waterings (1–14 days) |
| `number.*_max_duration` | Hard cap on watering time (1–60 min) |
| `number.*_soak_cycles` | Number of soak/cycle runs per session (1 = single run, 2–5 = split with pauses) |
| `number.*_soak_pause` | Minutes between soak cycles (5–120 min, default 30) |

## Services

### `adaptive_irrigation.water_zone`
Manually water a zone for a given duration.
```yaml
service: adaptive_irrigation.water_zone
data:
  zone_id: east
  duration_minutes: 10
```

### `adaptive_irrigation.cool_zone`

Run a cooling application on a zone. `duration_minutes` is optional and defaults
to the zone's configured cooling duration.

```yaml
service: adaptive_irrigation.cool_zone
data:
  zone_id: yard_west
  duration_minutes: 3
```

### `adaptive_irrigation.evaluate_now`
Force an immediate watering evaluation outside the 15-minute poll cycle. Also available as per-zone buttons on the Irrigation dashboard.
```yaml
service: adaptive_irrigation.evaluate_now
data:
  zone_id: east
```

### `adaptive_irrigation.calibration_status`
Post a persistent notification with a full calibration debug dump for all zones: current rate, data source (Store vs not yet computed), current soil, last watering context, and projected rate if the followup ran right now.
```yaml
service: adaptive_irrigation.calibration_status
```

### `adaptive_irrigation.force_calibration`
Manually trigger the calibration followup for a zone using the current soil reading. Use immediately after a manual watering run to seed calibration data without waiting for the next automatic cycle.
```yaml
service: adaptive_irrigation.force_calibration
data:
  zone_id: yard_west
```

## Decision Logic

Each poll cycle (every 15 min) per zone:

1. Master switch off, or Water Restriction on → skip everything (cooling included)
2. **Cooling** is evaluated first, because the cooling window (midday heat) is
   disjoint from the watering window (early morning) — see below
3. Auto watering switch off → skip watering
4. Outside the watering window → skip
5. Valve currently ON → skip; valve recently closed → wait for a genuine *rise*
   on the probe (sensor-free zones: 15-min flat wait)
6. Motion detected → defer (notify)
7. Wind > 25 mph → defer (notify)

**Zones with soil sensors:**

8. Within the dry-down lockout (18 h since the last soak) → skip
9. Soil above refill point → skip (status shows projected days to refill)
10. Soil at or below refill point, rain ≥ 0.15 in forecast → skip
11. Otherwise → **soak**

Duration = `(fill_target - current) / calibration_rate`, capped at `max_duration`,
falling back to `fallback_duration` until a calibration exists. Because the
deficit is large by design, `max_duration` usually governs — set it to a real
deep-soak length, not a top-up length.

**Sensor-free zones (drip/trees):** unchanged — peer-trend inference against
`water_interval_days`, duration `fallback_duration`. Cooling never applies;
syringing is a turf practice.

## Cooling

Cooling runs when **all** of the following hold:

- a root-zone temperature sensor is configured and `Heat Cooling` is on
- inside the cooling window (default 11:00–18:00; the end is clamped to 18:00 in
  code — a canopy left wet overnight invites fungal disease)
- root-zone temperature ≥ the zone's threshold **and still rising**
- under the daily run limit, and past the minimum interval since the last run
- not irrigated in the last 3 hours, soil below the moisture ceiling
- wind under the cooling limit, no meaningful rain forecast

The rising-temperature condition is what lets each zone self-time. A zone that
peaks at midday arms late morning; a west exposure that peaks late afternoon
arms then. No per-zone schedule to maintain, and it tracks seasonal drift in sun
angle automatically.

Cooling is deliberately **not** irrigation: it never sets `last_watered`, never
starts a calibration sample, and never counts toward the dry-down interval.

### A note on what cooling can and cannot do

Syringing shaves the peak off a temperature spike. It cannot make a full-sun
site hospitable to cool-season grass in high summer. If a zone runs 95–115 °F at
the root zone for hours a day, the limiting factor is heat, not water, and the
durable fixes are mowing height, shade, soil organic matter, and species choice.
Root growth stops around 80 °F and roots die back above roughly 85 °F.

## Setting Refill Point and Fill Target

Absolute percentages are **not comparable between probes** — soil, depth and
calibration all differ. Derive both numbers per zone from that probe's own
history rather than copying values between zones:

- **Fill target** — what the probe reads a day after a deep soak, once drainage
  has finished. That's this zone's practical field capacity.
- **Refill point** — how far you're willing to let it dry. Lower means longer,
  deeper cycles and deeper roots over time.

**Do not lower the refill point on turf that is already stressed, or while the
root zone is hot.** Deliberate depletion is a spring and autumn technique. In
high summer on a struggling zone it accelerates dieback rather than driving
roots down.

Seedling mode bypasses this model entirely and uses its own threshold —
seedlings have no root system to deepen and must not be dried down.

## Running Alongside Existing Automations

The integration is safe to run in parallel with existing automations during a pilot. Two guards prevent double-watering:

1. **Soil-response guard** — after any watering, re-evaluation is blocked until a probe records a genuine *rise* after the valve closed. (Before 0.8.0 this compared `last_updated`, which on a change-only sensor meant the soil drying out could satisfy it.)
2. **Valve guard** — skips if the valve is currently ON, regardless of who opened it.
3. **Dry-down lockout** — no moisture-driven watering for 18 h after a soak.
4. **Foreign-run detection** — a run the integration did not start voids any
   in-flight calibration sample and resets the dry-down clock, so another
   controller's schedule can't be credited to our own run.

Recommended pilot sequence: enable east zone, observe for 2 weeks, then expand one zone at a time and disable the corresponding legacy automation actions.
