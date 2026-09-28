/**
 * The page cases for `/models`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, RUNG_ID, UNBROKEN } from "../pageFixtures";

/**
 * The models screen's five answers. Its own route's tiers, providers and unmeasured sentences
 * carry unbreakable tokens, the chain is `MATRIX`, and the spend line's department is one too,
 * because a department key sits in a `.fields__row` label rather than in a scrolling table. The
 * providers answer is editable and names a credential, so both controls and the vault's column are
 * drawn, and its unbroken provider, model and switcher all sit inside the two scrolling tables.
 */
const MODELS_AND_HEALTH = {
  "/api/v1/operate/models": {
    start: "2019-02-25T09:00:00Z",
    end: "2019-03-04T09:00:00Z",
    tiers: [{ tier: "main", handles: UNBROKEN }],
    lanes: [
      { lane: "fast", requests: 3 },
      { lane: "answer", requests: 7 },
    ],
    providers: [{ provider: UNBROKEN, description: UNBROKEN }],
    unmeasured: [{ measure: UNBROKEN, because: UNBROKEN }],
    fallbacks_fired: 4,
  },
  "/api/v1/models/providers": {
    profile: "hosted",
    providers: [
      {
        provider: UNBROKEN,
        description: UNBROKEN,
        hosted: true,
        switched_on: false,
        switched_by: UNBROKEN,
        switched_at: "2019-03-04T09:00:00Z",
        key_held: true,
        credential: { slot: UNBROKEN, description: UNBROKEN, held: true, set_at: "2019-03-04T09:00:00Z" },
      },
    ],
    rungs: [
      {
        rung_id: RUNG_ID,
        tier: "main",
        position: 0,
        role: "primary",
        deployment_id: UNBROKEN,
        provider: UNBROKEN,
        model: UNBROKEN,
        enabled: true,
        answers: false,
        skipped_because: "switched_off",
        told: "This provider is switched off on this screen, so nothing is sent to it.",
        state: "closed",
        measured: false,
        unhealthy_because: null,
        live_seen: 0,
        live_failed: 0,
        probes_seen: 2,
        probes_failed: 1,
        last_probe_at: "2019-03-04T09:00:00Z",
        last_live_at: null,
      },
    ],
    exhausted_tiers: ["main"],
    editable: true,
    profile_editable: true,
    vault: "ready",
    vault_told: "The secrets vault answered.",
    tiers: [
      { tier: "small", context_window: 128000, escalation_headroom: 0.8, configured: false },
      { tier: "main", context_window: 50000, escalation_headroom: 0.5, configured: true },
    ],
    residency: [
      {
        id: "44444444-4444-4444-8444-444444444444",
        scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
        allowed_regions: [UNBROKEN],
        on_prem_only: false,
        note: UNBROKEN,
        created_by: UNBROKEN,
        created_at: "2019-03-04T09:00:00Z",
      },
    ],
    depth_alerts: [
      {
        raised_at: "2019-03-04T09:00:00Z",
        level: "warning",
        tier: "main",
        depth: 2,
        served_by: UNBROKEN,
        reason: UNBROKEN,
        trace_id: UNBROKEN,
      },
    ],
  },
  "/api/v1/report/service-levels": {
    start: "2019-02-25T09:00:00Z",
    end: "2019-03-04T09:00:00Z",
    lanes: [
      {
        lane: "answer",
        objective_p95_ms: 8000,
        objective_success_rate: 0.99,
        p95_ms: 4100,
        success_rate: 1,
        requests: 7,
        met: true,
        shortfalls: [],
      },
    ],
  },
  "/api/v1/report/spend": {
    dimension: "department",
    built: true,
    lines: [{ key: UNBROKEN, cost_minor: 700 }],
    machine_included: false,
    total_minor: 700,
    as_of: "2019-03-04T09:00:00Z",
    freshness: "live",
    currency: "XXX",
    time_zone: "UTC",
  },
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/models": {
    address: "/models",
    signedIn: true,
    drawsValues: true,
    answers: MODELS_AND_HEALTH,
  },
};
