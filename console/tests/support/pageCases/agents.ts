/**
 * The page cases for `/agents`, `/agents/:agentId` and `/agents/:agentId/:tab`: the address each is
 * mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { MATRIX, type PageCase, UNBROKEN } from "../pageFixtures";

/** One agent's figures as `brain.console_stats_routes.AgentStatsView` sends them. */
const AGENT_STATS = {
  agent_id: "quote-helper",
  basis: "everyone",
  cost_basis: "everyone",
  currency: "SGD",
  last_active: "2019-03-04T09:42:00Z",
  at_least: false,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    runs: 391,
    answered: 360,
    nothing_returned: 31,
    p50_latency_ms: 1840.5,
    cost_minor: null,
  })),
  unrecorded: [{ figure: "model_cost", why: UNBROKEN }],
};

const WORKSPACE = {
  agent: {
    agent_id: "quote-helper",
    display_name: UNBROKEN,
    summary: UNBROKEN,
    owner_id: UNBROKEN,
    owner_name: UNBROKEN,
    template_id: UNBROKEN,
    template_version: 4,
    created_at: "2019-03-01T09:00:00Z",
    state: "enabled",
    leash_up_to: "assisted",
  },
  tabs: ["conversations", "settings"].map((tab) => ({ tab, label: tab, purpose: UNBROKEN })),
  // The capability block and the figures, whose widest values are a connector name, a skill
  // name and a sixty-four character digest, each a token with nowhere to break.
  skills: [{ name: UNBROKEN, digest: "d".repeat(64) }],
  connectors: { shown: [{ source: UNBROKEN, presence: "attached" }], overflow: 0 },
  channels: [{ channel: UNBROKEN, profile: "plain" }],
  divergent: ["persona"],
  headline: { basis: "own", range: "30d", spend_minor: 1234, runs: 7, recorded: true },
  composition: [
    {
      part: "persona",
      path: "persona",
      template: `"${UNBROKEN}"`,
      instance: `"${UNBROKEN}"`,
      source: "instance",
      set_by: "steward-one",
    },
  ],
  // The profile's tier and pinned model (M5.7.3), drawn on the Profile pane.
  profile: { tier: "main", model_pin_provider: null, model_pin_model: null },
};

/** One installed automation whose every drawn value is an unbreakable token, with both controls. */
const AGENT_AUTOMATIONS = {
  items: [
    {
      automation_id: "auto_one",
      name: `I ${UNBROKEN}`,
      runs_as: UNBROKEN,
      runs_as_name: UNBROKEN,
      schedule: UNBROKEN,
      next_run_at: null,
      paused_because: UNBROKEN,
      last_run: { finished_at: UNBROKEN, outcome: UNBROKEN, reason: null, result: [UNBROKEN] },
      start_confirmation: "a".repeat(64),
      start_becomes: UNBROKEN,
      stop_confirmation: "b".repeat(64),
      cannot_start: UNBROKEN,
    },
  ],
  result_rule: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/agents": {
    address: "/agents",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agents": {
        items: [
          {
            agent_id: "quote-helper",
            display_name: UNBROKEN,
            owner_id: UNBROKEN,
            owner_name: UNBROKEN,
            department: UNBROKEN,
            state: "enabled",
            leash_up_to: "assisted",
            ceiling: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
          },
        ],
        next_cursor: null,
        truncated: false,
      },
      // Each row's figures, from the shared stats route, `brain.console_stats_routes`.
      "/api/v1/console/agents/quote-helper/stats": AGENT_STATS,
    },
  },
  // The Dashboard, which the bare address opens: the workspace for the header, the figures from the
  // shared stats route, and, for a reader of the Automations tab, this agent's automations with their
  // controls, so those are held to a phone too. The Profile's model card is on its own view.
  "/agents/:agentId": {
    address: "/agents/quote-helper",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agents/quote-helper/workspace": {
        ...WORKSPACE,
        tabs: ["automations", "settings"].map((tab) => ({ tab, label: tab, purpose: UNBROKEN })),
      },
      "/api/v1/console/agents/quote-helper/stats": AGENT_STATS,
      "/api/v1/agents/quote-helper/automations": AGENT_AUTOMATIONS,
    },
  },
  // The Profile, the view with the most on it: the capabilities, the permissions, the leash and the
  // model card, which draws the order a question tries from the matrix (M5.7.3). The Automations
  // section's gallery and list are the same components they were, held by their own tests.
  "/agents/:agentId/:tab": {
    address: "/agents/quote-helper/profile",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agents/quote-helper/workspace": {
        ...WORKSPACE,
        profile: {
          tier: "main",
          model_pin_provider: null,
          model_pin_model: null,
          audience_level: "department",
          ceiling: {
            rows: UNBROKEN,
            reads: [UNBROKEN],
            reads_locked: false,
            tools: UNBROKEN,
            largest_effect: UNBROKEN,
            max_side_effect: "draft",
          },
          tools: [{ name: UNBROKEN, source: UNBROKEN, side_effect: "draft", description: UNBROKEN, within_ceiling: true }],
          leash: [{ target: UNBROKEN, rung: "assisted", rungs: ["assisted"], configured: true, acts: true, entries: [] }],
        },
      },
      "/api/v1/routing/rungs": MATRIX,
    },
  },
};
