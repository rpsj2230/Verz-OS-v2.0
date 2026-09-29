/**
 * The page cases for `/agents`, `/agents/:agentId` and `/agents/:agentId/:tab`, and for New agent,
 * the drafts list and one draft: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { MATRIX, type PageCase, UNBROKEN } from "../pageFixtures";
import { readConsoleFile } from "../repo";

/** One agent's figures as `brain.console_stats_routes.AgentStatsView` sends them. */
const AGENT_STATS = {
  agent_id: "quote-helper",
  basis: "everyone",
  cost_basis: "everyone",
  currency: "SGD",
  last_active: "2019-03-04T09:42:00Z",
  at_least: false,
  periods: ["7d", "30d", "90d", "mtd"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    runs: 391,
    messages: 360,
    answered: 360,
    nothing_returned: 31,
    p50_latency_ms: 1840.5,
    cost_minor: 18240,
    // The cost per person, whose widest value is a name with nowhere to break.
    callers: [{ principal_id: UNBROKEN, name: UNBROKEN, spend_minor: 18240 }],
  })),
  unrecorded: [],
  // The month against the agent's own budget, drawn for a reader of everybody's spend.
  projection: { spent_minor: 18240, projected_minor: 99999999, ceiling_minor: 50000, over_ceiling: true },
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

/** A draft's id, as `brain.agent_builder_routes` mints one. */
export const DRAFT_ID = "44444444-4444-4444-8444-444444444444";

/** One draft on the drafts list, as `AgentDraftSummary` sends it. */
export const DRAFT_SUMMARY = {
  draft_id: DRAFT_ID,
  agent_id: "quote_helper_ab12cd",
  name: UNBROKEN,
  kind: "new",
  state: "waiting",
  revision: 2,
  saved_at: "2019-03-04T09:00:00Z",
};

/** One draft, as `AgentDraftView` sends it, with the widest values its steps draw. */
const DRAFT_VIEW = {
  ...DRAFT_SUMMARY,
  document: {
    identity: {
      template_id: "quote_helper_ab12cd",
      version: 1,
      published_by: UNBROKEN,
      display_name: UNBROKEN,
      summary: UNBROKEN,
    },
    persona: UNBROKEN,
    tier: "main",
    skills: [],
    authority: { scope: { clauses: [] }, capabilities: [], allowed_tools: [], required_tools: [] },
    connectors: [],
    guardrails: { max_side_effect: "none", leash: [] },
    golden_set: [],
    placeholders: [],
  },
  problems: [UNBROKEN],
  acts: [{ revision: 2, act: "checked", at: "2019-03-04T09:00:00Z" }],
  yours: true,
  waiting_on_you: false,
  widened: [UNBROKEN],
  drawable_tools: [UNBROKEN],
  publish_unavailable: null,
};

/** The builder's form, which `tests/unit/test_builder_form.py` holds equal to the API's. */
const BUILDER_FORM: unknown = JSON.parse(readConsoleFile("tests/fixtures/manifest-form.json"));

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
      // The capability detail, whose widest values are a source, a projected field, a skill and a
      // predicate value, each a token with nowhere to break.
      "/api/v1/agents/quote-helper/capabilities": {
        agent_id: "quote-helper",
        availability: { level: "department", department: UNBROKEN, owner_id: UNBROKEN, reader_is_included: true, words: UNBROKEN },
        connectors: [{ source: UNBROKEN, presence: "attached", projects: [UNBROKEN], health: "degraded", checked_at: "2019-03-04T09:00:00Z" }],
        skills: [{ name: UNBROKEN, digest: "d".repeat(64), version: UNBROKEN, source: "upload", review: "approved", runs: 7, detachable: true }],
        unused_skills: [],
        usage_basis: "everyone",
        skills_editable: true,
        offers: [{ name: UNBROKEN, version: UNBROKEN, digest: "e".repeat(64), review: "pending", control: "review", route: "/skills/x" }],
        knowledge: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }], matched: 1, verified: 1, stale: 0, unverified: 0, at_least: false },
      },
      // The leash block: an entry, a move with its evidence, a trip with its metric, supervision
      // and an action waiting for a verdict, each value a token with nowhere to break.
      "/api/v1/agents/quote-helper/attachments": {
        agent_id: "quote-helper",
        carried: [{ name: UNBROKEN, source: UNBROKEN, description: UNBROKEN }],
        carried_connectors: [UNBROKEN],
        tools: [{ name: UNBROKEN, source: UNBROKEN, description: UNBROKEN }],
        connectors: [UNBROKEN],
        may_change_tools: true,
        may_change_connectors: true,
      },
      "/api/v1/agents/quote-helper/leash": {
        agent_id: "quote-helper",
        entries: [{ target: UNBROKEN, scope: { clauses: [] }, where: UNBROKEN, rung: "assisted", proposed: "autonomous" }],
        history: [
          { target: UNBROKEN, where: UNBROKEN, kind: "raised", was: "shadow", became: "assisted", at: "2019-03-04T09:00:00Z", approver: UNBROKEN, second_approver: UNBROKEN, clean_runs: 10, agreement_rate: 1, metric: "", measured: null, threshold: null },
          { target: UNBROKEN, where: "", kind: "tripped", was: "assisted", became: "shadow", at: "2019-03-05T09:00:00Z", approver: "", second_approver: "", clean_runs: null, agreement_rate: null, metric: UNBROKEN, measured: 0.5, threshold: 0.9 },
        ],
        supervision: { pinned_at: "2019-02-01T09:00:00Z", review_due_at: "2019-03-03T09:00:00Z", outcome: "extended", understood: 8, reviewed: 10, simulated: 10, held: true, due: true },
        awaiting: [{ action_digest: "d".repeat(64), target: UNBROKEN, route: "simulate", at: "2019-03-06T09:00:00Z" }],
        may_move: true,
        may_judge: true,
      },
    },
  },
  // New agent: start from scratch, or from a template the gallery offers.
  "/agents/new": {
    address: "/agents/new",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agent-templates": {
        items: [
          {
            template_id: UNBROKEN,
            version: 1,
            display_name: UNBROKEN,
            summary: UNBROKEN,
            published_by: UNBROKEN,
            origin: "built_in",
          },
        ],
        next_cursor: null,
        total: null,
        truncated: false,
      },
    },
  },
  // The reader's drafts and the publishes waiting for them.
  "/agents/drafts": {
    address: "/agents/drafts",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/agent-drafts": { items: [DRAFT_SUMMARY], waiting_for_you: [DRAFT_SUMMARY] } },
  },
  // One draft's Write step, the one with the most on it: the builder's whole form.
  "/agents/drafts/:draftId": {
    address: `/agents/drafts/${DRAFT_ID}`,
    signedIn: true,
    drawsValues: true,
    answers: { [`/api/v1/agent-drafts/${DRAFT_ID}`]: DRAFT_VIEW, "/api/v1/builder/form": BUILDER_FORM },
  },
  // Its Publish step, with the audience choice and the history.
  "/agents/drafts/:draftId/:step": {
    address: `/agents/drafts/${DRAFT_ID}/publish`,
    signedIn: true,
    drawsValues: true,
    answers: { [`/api/v1/agent-drafts/${DRAFT_ID}`]: DRAFT_VIEW },
  },
};
