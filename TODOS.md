# Adaptive Irrigation — Deferred Work

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
