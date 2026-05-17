# Adaptive Irrigation — Deferred Work

## Master Switch — Label/Logic Inversion

**Bug:** The master switch dashboard card currently reads "System Pause: on" when the system is running, which sounds like it's paused. "On" should mean active/running, not paused.

**Fix:** Two things need to change together:
1. Rename the entity — `_attr_name = "Adaptive Irrigation"` is too generic and doesn't signal on/off meaning. Change to `"Auto Watering"` (consistent with per-zone switches) or `"System Active"` so that `on = running` is obvious.
2. Update the dashboard card label from `"System Pause"` to match the new entity name.

**Do not invert the switch logic** — `on = zones can water`, `off = all zones paused` is correct in code. Only the label is wrong.



## Water Allowance / Resource Allocation

**Feature:** Per-session water budget that ranks zones by need and allocates valve time to the most water-stressed zones first before lower-priority ones run.

**Config additions (integration-level, set on first zone like weather entity):**
- `water_meter_entity` — a `sensor.*` entity tracking consumption (e.g. from a smart water meter, Flume, or Rachio); used to measure actual gallons/liters used per session
- `daily_allowance_gallons` (or liters) — hard cap on total water the integration is allowed to use per calendar day
- `flow_rate_gpm` per zone — static gallons-per-minute for each valve (needed to convert duration → volume since soil sensors don't measure flow)

**Logic changes:**
- Before each poll cycle, sum today's consumption from `water_meter_entity` against `daily_allowance_gallons`
- If allowance is exhausted → all zones return "Skipped — daily water budget reached"
- If allowance is partially used → remaining budget constrains how many zones can run and for how long
- Zone **priority ranking** when budget is limited: sort eligible zones by (threshold − current_moisture) / threshold — i.e., largest deficit relative to threshold runs first. Sensor-free zones rank below sensor zones. If two zones tie, higher ET wins.
- Watering is serialized (not concurrent) when a budget is active, so consumption can be tracked accurately between zones

**Why it matters:** Forces honest allocation of a scarce resource rather than every zone running independently and potentially blowing a water budget or overwhelm a low-flow well. Also surfaces water cost per zone over time.

**Open questions before implementing:**
- Is the water meter entity cumulative (total gallons ever) or a session/daily counter? Needs different delta logic.
- Does the allowance reset at midnight local time or on a rolling 24h window?
- Should allowance be per-day only, or also per-week (for drought restrictions)?
- Should zones be allowed to "borrow" from tomorrow's budget if today's is spent but moisture is critically low?
