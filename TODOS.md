# Adaptive Irrigation — Deferred Work

## Root-Training Controller (deferred from 0.8.0)

**Status: MEASUREMENT SHIPPED in 0.8.0, CONTROLLER DEFERRED**

0.8.0 records dry-down cycle length and the moisture peak each soak reaches.
What is *not* implemented is the controller that walks a zone's refill point
downward over successive cycles to deepen roots.

Deferred deliberately, for two reasons:

1. **No clean data to tune against yet.** Every dry-down cycle recorded before
   0.8.0 is contaminated — by external controller runs credited to our own, by
   soak cycling that delivered a fraction of what it announced, and by a
   calibration estimate that could only ratchet upward. Picking step sizes and
   thresholds now would mean guessing at constants there will be real data for
   after a few clean cycles.
2. **It must not run while the root zone is hot.** Root growth stops around
   80 °F and roots die back above roughly 85 °F. Deliberate depletion on turf
   that is already heat-stressed accelerates dieback instead of driving roots
   down. The gate should be measured soil temperature
   (`ROOT_TRAINING_MAX_SOIL_TEMP`), not a calendar date.

When picking this up:
- Require N consecutive cycles where the zone recovered fully to its fill target
  and the dry-down did not shorten, before stepping the refill point down.
- Step 2–3 points per cycle at most, with a per-zone hard floor.
- Gate on sustained root-zone temperature below the threshold, not on the month.
- Revert a step automatically if the next cycle's dry-down accelerates.

---

## Per-Zone Cooling Retiming Data

**Status: OPEN**

Cooling arms on a rising root-zone temperature, which self-times each zone
without a schedule. Worth revisiting after a few weeks of `Last Cooling Delta`
data to confirm the rising-edge gate is catching each zone's actual peak, and
whether a secondary "sustained above a high-water mark" trigger is needed for a
zone that parks at a high temperature while technically declining.

---

## Entity ID Collision — Yard Middle Soak Entities

**Status: OPEN (cosmetic, but a trap)**

`number.yard_west_adaptive_irrigation_yard_middle_soak_cycles` and
`..._soak_pause` carry a `yard_west_` object-id prefix on `yard_middle`
entities. They currently work — the dashboard references the odd IDs correctly —
but the naming will mislead anyone editing later. Fixing requires an entity
registry rename plus a matching dashboard update, done together.

---

## Master Switch — Label/Logic Inversion

**Status: SHIPPED in 0.6.3** — `_attr_name` changed to `"System Active"`.

---

## Water Allowance / Resource Allocation

**Status: PARTIALLY SHIPPED in 0.6.3**

Shipped:
- Water Restriction switch (blocks all zones)
- Daily water budget cap (`daily_budget_gallons`) — gates and truncates zone sessions
- Daily Water Used sensor — Flume/cumulative meter integration; falls back to `duration × flow_rate` estimate
- Flow Rate per zone (`flow_rate_gpm`) number entity
- Budget resets at **midnight local time** (resolved open question)

**Remaining — Priority Orchestration (deferred):**

Zone priority ranking (driest-first serialized allocation) requires a session-level orchestrator that coordinates across all zone coordinators before any valve opens. This breaks the current independent-coordinator model where each zone evaluates and acts in isolation. Implementing it correctly requires:
- A shared lock/queue in `hass.data[DOMAIN]` so only one zone runs at a time when budget is active
- A ranking pass at the start of each session (sort by largest moisture deficit) before any zone fires
- Cross-zone signaling so zones know to wait their turn

This is a significant architectural change — defer to a future 0.7.x release.
