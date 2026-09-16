/**
 * Every page this console registers, held to a phone's width, and why that is asserted as a
 * cascade rather than as a measurement.
 *
 * **What was wrong, measured rather than reasoned about.** On 2026-09-15 every route in
 * `App.tsx` was rendered with values from the API that have no break in them, the markup was
 * written out beside the console's own four stylesheets, and each page was opened in headless
 * Chrome inside an iframe 360 pixels wide. The iframe is what sets the viewport: a headless
 * window will not go below 526 pixels, so a window size alone measures nothing at a phone's
 * width. Five views scrolled sideways. The overview reached 855 pixels, and the agent
 * workspace 911 on its first tab, on its profile pane and at a tab's own address, because
 * `.fields__row` put a label 12rem wide beside a value that could not shrink below its longest
 * word. The agent roster reached 599 once a display name was one unbroken word, because nothing
 * let a link break inside a word. After the change, all fifteen views measured a document
 * width of 360 at 360 and 412 at 412, and at 1280 none overflowed and the sidebar was back.
 *
 * **What these tests can prove, and what they cannot.** jsdom matches selectors and lays out
 * nothing, so no test here can say a page is 360 pixels wide, and none claims to. What
 * `support/cascade.ts` gives them is which declaration wins for a rendered element when the
 * queries a 360 pixel screen matches are applied and the others are not. The declarations
 * asserted are the ones that decided the measurement: whether a value may wrap and whether a
 * token may break, whether the navigation stacks above the page, and how tall a link is. If a
 * browser stopped honouring one of them these tests would not notice, and if a font's metrics
 * made a page wider they would not notice either. That residue is what the measurement is for,
 * and it was not committed as a test because it needs a browser this suite does not have.
 *
 * **Every registered page, not a list of the ones somebody remembered.** The patterns are read
 * out of the route table, and a route with no entry here fails the first test. That is how a
 * page added next month gets a phone case on the day it is added rather than on the day
 * somebody opens it on a phone.
 *
 * **The narrow screen is every sheet's base case.** Approvals arrive on phones, and the page
 * they arrive on sits inside the shell, so a mobile-first approvals sheet inside a shell whose
 * phone layout was a `max-width` patch was mobile-first in one of its two halves. No sheet in
 * the console now writes a `max-width` query, and a wider screen is an enhancement inside a
 * `min-width` one.
 */

import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { CALLBACK_PATH, SIGNED_OUT_PATH } from "../src/auth/constants";
import { FIRST_RUN_PATH } from "../src/setup/wizard";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import {
  CONSOLE_SHEETS,
  appliesAt,
  consoleRules,
  declared,
  inherited,
  pixels,
  type OrderedRule,
} from "./support/cascade";
import { parseCss } from "./support/css";
import { readConsoleFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";

/** The narrowest phone the console is held to, in CSS pixels. */
const PHONE_PX = 360;
/** A desktop screen, for the sibling that proves the phone rules are a base and not the lot. */
const WIDE_PX = 1280;
/** The smallest tap target, in CSS pixels. */
const TAP_TARGET_PX = 44;

/** A value with nowhere to break, which is what an identifier from the API usually is. */
const UNBROKEN = `UNBROKEN${"x".repeat(72)}`;

const RUNG_ID = "11111111-1111-4111-8111-111111111111";

interface PageCase {
  /** The address mounted for this pattern. */
  readonly address: string;
  /** Whether the page sits behind the session guard and so needs a signed-in console. */
  readonly signedIn: boolean;
  /** The stand-in API, by path. */
  readonly answers: Readonly<Record<string, unknown>>;
  /** Whether the page draws a value the API sent, so the unbroken value must appear on it. */
  readonly drawsValues: boolean;
}

function card(id: string): Record<string, unknown> {
  return {
    suspension_id: id,
    artefact: `ticket.update_status on ticket\n  note: ${UNBROKEN}`,
    runs_as: UNBROKEN,
    raised_at: "2019-03-04T09:00:00Z",
    expires_at: "2019-03-04T13:00:00Z",
  };
}

const MATRIX = {
  items: [
    {
      id: RUNG_ID,
      tier: "main",
      position: 0,
      role: "primary",
      scope: {},
      deployment_id: UNBROKEN,
      provider: "anthropic",
      model: "claude-sonnet-5",
      attempts: 1,
      timeout_seconds: 12,
      max_concurrency: 40,
      enabled: true,
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
};

const CLASSIFICATION = {
  entity: "price_list",
  columns: [
    {
      column: "cost",
      required_capability: "read:price_list.cost",
      classification: "confidential",
      derived_from: [UNBROKEN],
    },
  ],
  epoch: "EPOCH-SENTINEL",
  editable: true,
};

const WORKSPACE = {
  agent: {
    agent_id: "quote-helper",
    display_name: UNBROKEN,
    summary: UNBROKEN,
    owner_id: UNBROKEN,
    template_id: UNBROKEN,
    template_version: 4,
  },
  tabs: ["conversations", "settings"].map((tab) => ({ tab, label: tab, purpose: UNBROKEN })),
  // The capability block and the figures, whose widest values are a connector name, a skill
  // name and a sixty-four character digest, each a token with nowhere to break.
  skills: [{ name: UNBROKEN, digest: "d".repeat(64) }],
  connectors: { shown: [{ source: UNBROKEN, presence: "attached" }], overflow: 0 },
  channels: [{ channel: UNBROKEN, profile: "plain" }],
  divergent: ["persona"],
  headline: { basis: "own", range: "30d", spend_minor: 1234, runs: 7 },
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
};

/** The automation gallery on an agent's Automations tab, whose outcome and schedule cannot break. */
const AUTOMATION_GALLERY = {
  items: [
    {
      template_id: "weekly_work_summary",
      version: 1,
      name: `I ${UNBROKEN}`,
      summary: UNBROKEN,
      schedule: UNBROKEN,
      installed_as: null,
      installable: true,
    },
  ],
  installing: UNBROKEN,
};

/** One page of people, whose subject key and capability are both unbreakable tokens. */
const PEOPLE = {
  items: [{ subject: `principal:${UNBROKEN}`, capabilities: [UNBROKEN] }],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
  staleness: null,
};

/** One scope, whose slug and whose clause value are both unbreakable tokens. */
const SCOPES = {
  items: [
    {
      slug: UNBROKEN,
      label: UNBROKEN,
      is_department: true,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  departments: [UNBROKEN],
  staleness: null,
};

/** One staff source whose setting names and whose meaning are both unbreakable tokens. */
const STAFF_SOURCES = {
  options: [
    {
      name: UNBROKEN,
      meaning: UNBROKEN,
      reads_a_list: true,
      needs: [UNBROKEN],
      unsupplied: [UNBROKEN],
      chosen: true,
    },
  ],
  // Ready, with no refusal, and that is the loop's constraint rather than the screen's: a
  // refusal is drawn in a `Notice`, `Notice` carries `role="status"`, and `mount` reads that as
  // a page still asking. The values this test is about are the identifier-shaped ones, which
  // are the name, the setting names and the meaning; a refusal is a sentence with spaces in it.
  // What a refusal draws is held in `tests/staff-sources-page.test.tsx`.
  selection: {
    name: UNBROKEN,
    meaning: UNBROKEN,
    reads_a_list: true,
    unsupplied: [UNBROKEN],
    refusal: "",
    ready: true,
  },
  not_written_here: UNBROKEN,
};

/**
 * One skill, whose name, whose pinned digest and whose agent are all unbreakable tokens.
 *
 * A digest is sixty-four characters with nowhere to break and it is on every row of this
 * screen, which makes it the widest single value the console renders anywhere.
 */
/**
 * One ledger entry whose actor, subject and detail are unbreakable tokens, and the same actor
 * offered in the Who filter, which is the one value on the page outside the table.
 */
const AUDIT = {
  items: [
    {
      at: "2019-03-04T09:00:00Z",
      action: "grant",
      actor_id: UNBROKEN,
      subject_kind: "principal",
      subject_id: UNBROKEN,
      details: { capability: UNBROKEN },
    },
  ],
  next_cursor: null,
  order: "newest",
  actions: ["grant"],
  subject_kinds: ["principal"],
  actors: [UNBROKEN],
};

/**
 * One session whose person, principal id and department are unbreakable, and the two sentences
 * the API serves beside the list, which sit outside the table and must wrap.
 */
const SESSIONS = {
  items: [
    {
      session_id: "kc-1",
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      second_factor: true,
      signed_in_at: "2019-03-04T09:00:00Z",
      lapses_at: "2019-03-04T19:00:00Z",
      yours: false,
      endable: true,
    },
  ],
  truncated: false,
  ending: UNBROKEN,
  appears: UNBROKEN,
};

/**
 * One link marked as the last administrator's, so the served sentence about it is drawn, and the
 * sentence about where the account is kept, both outside the table.
 */
const SIGN_IN_LINKS = {
  items: [
    {
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      linked_at: "2019-03-04T09:00:00Z",
      last_administrator: true,
      yours: false,
    },
  ],
  truncated: false,
  account: UNBROKEN,
  unlinking: UNBROKEN,
  last_administrator: UNBROKEN,
};

/**
 * What the live runs screen is answered: one control running and one owed, each with a name and a
 * sentence that are unbreakable tokens. No refusal, because a `Notice` carries `role="status"` and
 * `mount` reads that as a page still asking.
 */
const LIVE_RUNS = {
  as_of: "2019-03-04T09:00:00Z",
  running: [
    {
      control: UNBROKEN,
      keeps_true: UNBROKEN,
      started_at: "2019-03-04T07:00:00Z",
      report_only: true,
      stalled: true,
    },
  ],
  waiting: [
    {
      control: UNBROKEN,
      keeps_true: UNBROKEN,
      due_since: "2019-03-04T06:00:00Z",
      late_by_seconds: 10800,
      first_run: false,
    },
  ],
  stalled_after_seconds: 600,
  requests_in_flight_are_not_recorded: true,
  queue_is_not_readable: true,
  no_run_can_be_stopped: true,
};

/**
 * The models screen's four answers. Its own route's tiers, providers and unmeasured sentences
 * carry unbreakable tokens, the chain is `MATRIX`, and the spend line's department is one too,
 * because a department key sits in a `.fields__row` label rather than in a scrolling table.
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
    breaker_state_is_not_recorded: true,
    key_status_is_not_served: true,
  },
  "/api/v1/routing/rungs": MATRIX,
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
  },
};

const DEPARTMENTS = {
  departments: [
    {
      slug: UNBROKEN,
      name: UNBROKEN,
      teams: [{ slug: UNBROKEN, name: UNBROKEN }],
      members: [{ principal_id: UNBROKEN, display_name: UNBROKEN, disabled: true }],
    },
  ],
  unplaced: [{ principal_id: `${UNBROKEN}0`, display_name: UNBROKEN, disabled: false, department: UNBROKEN }],
  truncated: true,
  staleness: null,
  teams: UNBROKEN,
  leads: UNBROKEN,
  counted: UNBROKEN,
};

const ELEVATION = {
  prompt: UNBROKEN,
  holds_nothing_standing: false,
  may_authorise: true,
  reasons: [UNBROKEN],
  longest_hours: 4,
  what: UNBROKEN,
  recorded: UNBROKEN,
  authorising: UNBROKEN,
};

const ACCESS_REVIEW = {
  items: [
    {
      kind: "pack",
      row_id: UNBROKEN,
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      capabilities: [UNBROKEN],
      pack: UNBROKEN,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
      granted_by: UNBROKEN,
      reason: UNBROKEN,
      granted_at: "2019-03-04T09:00:00Z",
      lapses_at: null,
      last_decision: "keep",
      last_decided_by: UNBROKEN,
      last_decided_at: "2019-04-01T09:00:00Z",
    },
  ],
  truncated: true,
  shows: UNBROKEN,
  keeping: UNBROKEN,
  removing: UNBROKEN,
};

const SUBSCRIBERS = {
  items: [
    {
      subscriber_id: UNBROKEN,
      endpoint: UNBROKEN,
      kinds: [UNBROKEN],
      active: false,
      created_by: UNBROKEN,
      last_delivered_at: null,
    },
  ],
  findings: [UNBROKEN],
  kinds: [UNBROKEN],
  staleness: null,
  stopping: UNBROKEN,
  scope: UNBROKEN,
  told: UNBROKEN,
};

const SKILLS = {
  items: [
    {
      name: UNBROKEN,
      pinned_by: [{ agent_id: UNBROKEN, digest: "d".repeat(64) }],
      versions_differ: true,
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  queue: { entries: [], waiting: 0, edits: 0, stale: 0 },
  review_is_not_recorded: true,
  assignment_is_not_writable: true,
};

/** Every registered route pattern, and what to mount for it. */
const WEBHOOKS = {
  manageable: true,
  vault: "unreachable",
  vault_told: UNBROKEN,
  subscribers: [
    {
      subscriber_id: UNBROKEN,
      endpoint: `https://${UNBROKEN}.example.test/`,
      kinds: ["approval.requested"],
      active: true,
      created_by: UNBROKEN,
      created_at: "2019-03-04T09:00:00Z",
      deactivated_at: null,
      last_delivered_at: null,
      secret_held: null,
      secret_written_at: null,
      deliveries: [
        {
          kind: "approval.requested",
          state: "pending",
          attempts: 0,
          occurred_at: "2019-03-04T09:00:00Z",
          last_attempt_at: null,
          reason: UNBROKEN,
        },
      ],
      changes: [
        {
          change: "registered",
          changed_by: UNBROKEN,
          changed_at: "2019-03-04T09:00:00Z",
          secret_written_at: null,
        },
      ],
    },
  ],
  findings: [UNBROKEN],
  kinds: ["automation.run_finished", "operation.settled", "connector.health_changed", "approval.requested"],
  delivery: UNBROKEN,
  inbound: {
    channels: ["email", "slack"],
    channels_told: UNBROKEN,
    automation_path: `/api/v1/${UNBROKEN}`,
    automation_told: UNBROKEN,
  },
  registering: UNBROKEN,
  replacing: UNBROKEN,
  switching_off: UNBROKEN,
  secret_minimum: 32,
};

const STORAGE = {
  buckets: [
    {
      name: UNBROKEN,
      holds: UNBROKEN,
      retention_days: 30,
      retention_reason: UNBROKEN,
      versioned: false,
      public_read: false,
      kinds: [UNBROKEN],
    },
  ],
  findings: [UNBROKEN],
  endpoint: { address: `http://${UNBROKEN}:8333`, prefix: UNBROKEN, from_default: false, told: UNBROKEN },
  connection: UNBROKEN,
  usage: UNBROKEN,
  names: UNBROKEN,
  retention: UNBROKEN,
  read_at: "2019-03-04T09:00:00Z",
};

const DATA_TRANSFER = {
  catalogue: [
    { key: "audit_trail", label: UNBROKEN, direction: "export", carries: UNBROKEN, runs: true, told: UNBROKEN },
    { key: "skills", label: UNBROKEN, direction: "import", carries: UNBROKEN, runs: false, told: UNBROKEN },
  ],
  reasons: ["regulatory_request"],
  exportable: true,
  exports: [
    {
      export_id: "11111111-1111-4111-8111-111111111111",
      data_set: "audit_trail",
      reason: "regulatory_request",
      reason_reference: UNBROKEN.slice(0, 64),
      produced_at: "2019-03-04T09:00:00Z",
      first_seq: 0,
      last_seq: 1,
      entries: 2,
      verified: true,
      document_digest: "a".repeat(64),
    },
  ],
  export_told: UNBROKEN,
  document_told: UNBROKEN,
  own_exports_told: UNBROKEN,
  max_entries: 50000,
};

const PAGES: Readonly<Record<string, PageCase>> = {
  "/": {
    address: "/",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/me": {
        principal_id: UNBROKEN,
        display_name: UNBROKEN,
        primary_department: UNBROKEN,
        employment: "employee",
        assurance: "aal2",
        channel: "web",
        ent_hash: "f".repeat(64),
      },
    },
  },
  // No answers, and `drawsValues` false, because this page asks nothing until somebody types
  // a question and presses a button: mounting it draws the form and the sentence saying
  // nothing has been asked. What it draws once an answer arrives is held to the same rules in
  // `tests/ask-page.test.tsx`, which can drive the asking this loop cannot.
  "/ask": { address: "/ask", signedIn: true, drawsValues: false, answers: {} },
  "/records": { address: "/records", signedIn: true, drawsValues: false, answers: {} },
  "/records/:entity": {
    address: "/records/customer_account",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/records/customer_account": {
        items: [{ id: UNBROKEN, owner: UNBROKEN }],
        next_cursor: null,
        locked: [],
        source: "a-system-of-record",
        fetched_at: "2019-03-04T09:00:00Z",
        truncated: false,
      },
    },
  },
  "/routing": {
    address: "/routing",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/routing/rungs": MATRIX },
  },
  "/routing/:rungId": {
    address: `/routing/${RUNG_ID}`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/routing/rungs": MATRIX },
  },
  "/classification": { address: "/classification", signedIn: true, drawsValues: false, answers: {} },
  "/classification/:entity": {
    address: "/classification/price_list",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/classifications/price_list": CLASSIFICATION },
  },
  "/classification/:entity/:column": {
    address: "/classification/price_list/cost",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/classifications/price_list": CLASSIFICATION },
  },
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
            department: UNBROKEN,
            ceiling: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
          },
        ],
      },
    },
  },
  // The catalogue. Its widest values are a template slug and the publisher's principal id,
  // which are both identifiers, and the summary is a sentence the API wrote.
  "/agent-templates": {
    address: "/agent-templates",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agent-templates": {
        items: [
          {
            template_id: UNBROKEN,
            version: 2,
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
  "/agents/:agentId": {
    address: "/agents/quote-helper",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/agents/quote-helper/workspace": WORKSPACE },
  },
  // The Automations tab, so the gallery it draws is held to a phone as well as the workspace.
  "/agents/:agentId/:tab": {
    address: "/agents/quote-helper/automations",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agents/quote-helper/workspace": {
        ...WORKSPACE,
        tabs: ["automations", "settings"].map((tab) => ({ tab, label: tab, purpose: UNBROKEN })),
      },
      "/api/v1/agents/quote-helper/automation-templates": AUTOMATION_GALLERY,
    },
  },
  "/approvals": {
    address: "/approvals",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/approvals": { items: [card("sus_1")], truncated: false } },
  },
  "/approvals/:suspensionId": {
    address: "/approvals/sus_1",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/approvals/sus_1": card("sus_1") },
  },
  // The three Report screens. Each draws a table of figures beside a key that can be an
  // unbroken identifier, which is the shape that took five views off the side of a phone
  // before `.grid__scroll` existed: the table scrolls and the document does not.
  "/service-levels": {
    address: "/service-levels",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/service-levels": {
        start: "2019-03-04T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        lanes: [
          {
            lane: UNBROKEN,
            objective_p95_ms: 2000,
            objective_success_rate: 0.99,
            p95_ms: 1200,
            success_rate: 0.995,
            requests: 40,
            met: true,
            shortfalls: [UNBROKEN],
          },
        ],
      },
    },
  },
  "/spend": {
    address: "/spend",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/spend": {
        dimension: "department",
        built: true,
        lines: [{ key: UNBROKEN, cost_minor: 700 }],
        machine_included: false,
        total_minor: 700,
        as_of: "2019-03-04T09:00:00Z",
        freshness: "live",
      },
    },
  },
  "/adoption": {
    address: "/adoption",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/adoption": {
        items: [{ department: UNBROKEN, questions: 12, people: 3 }],
        next_cursor: null,
        total: null,
        truncated: false,
      },
    },
  },
  // The four govern screens. Every one of them draws an identifier from the API with nowhere to
  // break: a subject key, a capability, a scope slug and a clause are all one token, and a
  // capability is the longest of them. The people screen is mounted twice, once from the menu
  // and once at a subject's own address, because the second draws a second list and a form.
  "/people": {
    address: "/people",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/people": PEOPLE },
  },
  "/people/:subject": {
    address: `/people/${encodeURIComponent(`principal:${UNBROKEN}`)}`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/people": PEOPLE, "/api/v1/govern/scopes": SCOPES },
  },
  "/roles": {
    address: "/roles",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/roles": {
        roles: [
          {
            role: UNBROKEN,
            exists_to: UNBROKEN,
            typical_count: UNBROKEN,
            scope_required: true,
          },
        ],
        holders_are_not_recorded_yet: true,
      },
    },
  },
  "/capabilities": {
    address: "/capabilities",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/capabilities": {
        capabilities: [{ capability: UNBROKEN, description: UNBROKEN }],
        staleness: null,
      },
    },
  },
  "/scopes": {
    address: "/scopes",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/scopes": SCOPES },
  },
  // Skills, mounted twice for the people screen's reason: once from the menu and once at one
  // skill's own address, because the second draws a second list under the open skill.
  "/skills": {
    address: "/skills",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/skills": SKILLS },
  },
  "/skills/:name": {
    address: `/skills/${encodeURIComponent(UNBROKEN)}`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/skills": SKILLS },
  },
  // Staff sources. The unbreakable token is a setting name and a source's meaning, which are
  // the two values on this screen with nowhere to wrap: a setting name is an identifier and a
  // meaning is a paragraph the API wrote. The trial is not answered here, because it is asked
  // for by a button this loop does not press; what it draws once a plan arrives is held to the
  // same rules in `tests/staff-sources-page.test.tsx`.
  "/staff_sources": {
    address: "/staff_sources",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/staff_sources": STAFF_SOURCES },
  },
  // The five install screens. Each draws a value the API sent, so the unbroken identifier is on
  // every one of them: a fact's value, a release statement, a copy's timestamp, a ceiling's name
  // and a database's name are all identifiers with nowhere to break, which is the shape that
  // took three other pages past a phone's width before anybody measured.
  "/install": {
    address: "/install",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install": {
        facts: [
          { name: "profile", source: "declared", value: "standard", because: "" },
          { name: "release", source: "measured", value: UNBROKEN, because: UNBROKEN },
        ],
      },
    },
  },
  "/updates": {
    address: "/updates",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/updates": {
        running: {
          tag: "",
          facts: [{ name: "built commit", source: "measured", value: UNBROKEN, because: UNBROKEN }],
          cannot_say: UNBROKEN,
        },
        told: null,
        unanswered: {
          why: "no release list is configured",
          detail: UNBROKEN,
          at: "2019-03-04T09:00:00Z",
        },
        standing: "unknown running",
        says: UNBROKEN,
        what_to_do: UNBROKEN,
        told_days_ago: null,
        goes_off_after_days: 30,
      },
    },
  },
  "/recovery": {
    address: "/recovery",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/recovery": {
        rehearsal: {
          every_days: 7,
          copies_kept_days: 35,
          promised_recovery_seconds: 7200,
          manifest_ends: ".manifest.json",
          record_ends: ".drill.json",
          no_control_here: UNBROKEN,
        },
        panel: {
          profile: "standard",
          copies: [
            {
              coverage: "database",
              facts: [
                {
                  name: "database: newest copy reaches",
                  source: "measured",
                  value: UNBROKEN,
                  because: UNBROKEN,
                },
              ],
              within_objective: false,
              objective_seconds: 3600,
            },
          ],
          last_verified: {
            name: "last verified restore",
            source: "unknown",
            value: "",
            because: UNBROKEN,
          },
          measured_rto_seconds: null,
          assurance: "never verified",
          says: UNBROKEN,
          what_to_do: UNBROKEN,
          drill_is_due: true,
          // Empty, and not because the unreadable case does not matter. `ui/Notice.tsx` carries
          // `role="status"`, which is what `mount` above waits for the absence of before it
          // measures, so a page whose steady state holds a notice never settles here. The two
          // notice states on these screens are held by `tests/install-pages.test.tsx` instead.
          unreadable: [],
        },
        unread: "",
      },
    },
  },
  "/limits": {
    address: "/limits",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/limits": {
        ceilings: [{ name: UNBROKEN, per_day: 5000, raisable: true, derived: false }],
        throttled: [
          { scope: "principal", subject: UNBROKEN, limit: 60, retry_after_seconds: 12 },
        ],
        unread: "",
      },
    },
  },
  // Scheduled jobs. The control name, the sentence, the report and the person who paused are
  // drawn inside the scrolling table; the switched-off sentence is outside it.
  "/jobs": {
    address: "/jobs",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/jobs": {
        as_of: "2019-03-06T09:00:00Z",
        jobs: [
          {
            control: UNBROKEN,
            keeps_true: UNBROKEN,
            every_seconds: 3600,
            destructive: false,
            report_only: true,
            runnable: true,
            needs: null,
            last_started_at: "2019-03-06T08:00:00Z",
            last_finished_at: "2019-03-06T08:00:02Z",
            last_outcome: "ok",
            last_report: UNBROKEN,
            last_failure_kind: null,
            last_succeeded_at: "2019-03-06T08:00:02Z",
            owed: true,
            late_by_seconds: 7200,
            paused: true,
            pause_changed_by: UNBROKEN,
            pause_changed_at: "2019-03-06T08:30:00Z",
            run_requested_at: "2019-03-06T08:40:00Z",
            run_requested_by: UNBROKEN,
            run_pending: true,
          },
        ],
        controls_switched_on: false,
        may_control: true,
        no_run_can_be_stopped: true,
        only_the_last_change_is_kept: true,
      },
    },
  },
  "/errors": {
    address: "/errors",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/errors": {
        start: "2019-02-27T09:00:00Z",
        end: "2019-03-06T09:00:00Z",
        jobs: [
          {
            control: UNBROKEN,
            started_at: "2019-03-06T08:00:00Z",
            finished_at: "2019-03-06T08:00:02Z",
            kind: UNBROKEN,
          },
        ],
        jobs_truncated: true,
        requests: [
          {
            reference: UNBROKEN,
            received_at: "2019-03-06T08:30:00Z",
            lane: "model",
            status: "degraded",
            duration_ms: 812.4,
          },
        ],
        requests_truncated: true,
        process_log_is_not_kept: true,
        failure_messages_stay_on_the_server: true,
      },
    },
  },
  // Prompts. Instructions are drawn a paragraph per line, outside any table, so an unbroken
  // line is the case that would overflow a phone.
  "/prompts": {
    address: "/prompts",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/prompts": {
        house_rules: [UNBROKEN],
        output_lengths: [{ name: "brief", instruction: UNBROKEN }],
        agents: [
          {
            agent_id: UNBROKEN,
            display_name: UNBROKEN,
            department: UNBROKEN,
            instructions: `${UNBROKEN}\n${UNBROKEN}`,
            template_id: UNBROKEN,
            template_version: 3,
            template_instructions: UNBROKEN,
            overridden: true,
            set_by: UNBROKEN,
            set_at: "2019-03-05T09:00:00Z",
            effective_hash: "a".repeat(64),
            installed: true,
            editable: true,
          },
        ],
        max_chars: 2000,
        editing_switched_on: true,
        system_instructions_are_product_text: true,
        no_model_is_called_yet: true,
        only_the_last_change_is_kept: true,
      },
    },
  },
  "/features": {
    address: "/features",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/features": {
        features: [
          {
            name: "schedule_control",
            title: UNBROKEN,
            what: UNBROKEN,
            while_off: UNBROKEN,
            on: true,
            read_by: [UNBROKEN],
            changed_by: UNBROKEN,
            changed_at: "2019-03-04T09:00:00Z",
          },
        ],
        components_are_chosen_by_the_profile: true,
        plugins_have_no_loader: true,
        only_the_last_change_is_kept: true,
      },
    },
  },
  "/connections": {
    address: "/connections",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/capacity": {
        memory: {
          profile: "standard",
          host_total_mib: 16000,
          declared_mib: 4000,
          deployed_mib: null,
          // Empty for the reason the recovery case above gives: a budget finding draws a notice,
          // and a notice never stops looking like a page that is still asking to `mount`.
          breaches: [],
          unbudgeted: [],
        },
        connections: [{ database: UNBROKEN, admissible: 100, demand: 60, headroom: 40 }],
      },
    },
  },
  // Connectors. Every text column on it is either an identifier from the API or a sentence, and
  // the identifier is the source's own name, which is the shape that took five views off the
  // side of a phone before `.grid__scroll` existed. The unread and failure states draw a notice
  // and are held in `tests/connectors-page.test.tsx` instead, for the recovery case's reason.
  "/connectors": {
    address: "/connectors",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/connectors": {
        connectors: [
          {
            name: UNBROKEN,
            wiring: "rest",
            credential: `Held in the vault, borrowed as application. ${UNBROKEN}`,
            budget: `60 requests a minute. ${UNBROKEN}`,
            projected_fields: 9,
            checked_at: "2019-03-04T09:00:00Z",
            health: "ok",
            lifecycle: "enabled",
            serving: true,
            version: "1.0.0",
            reaches: `Reaches view ${UNBROKEN}, and nothing else in the source.`,
            access: UNBROKEN,
            permission_sync: UNBROKEN,
          },
        ],
        unread: "",
        connecting: UNBROKEN,
        copy_policy: [{ what: UNBROKEN, verdict: "projected", why: UNBROKEN }],
        budget_unread: UNBROKEN,
        may_connect: true,
      },
    },
  },
  // Knowledge. The item reference is an identifier with no break in it, which is why the library
  // table sits in `.grid__scroll`; the department name is a chip outside the table and has to be
  // able to wrap. `truncated` is true so the full-page sentence is drawn as well.
  "/library": {
    address: "/library",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/library": {
        items: [{ item_id: UNBROKEN, level: "department" }],
        next_cursor: null,
        total: null,
        truncated: true,
        departments: [UNBROKEN],
        staleness: null,
        only_existence_and_reach_are_shown: true,
        freshness_and_use_are_not_measured: true,
      },
    },
  },
  // Learning. Recorded rather than not, so all three tier tables are drawn and a memory id, a
  // department and a change kind each arrive unbroken; the change kind also sits in the four-tier
  // card outside any table.
  "/learning": {
    address: "/learning",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/learning": {
        basis: "everyone",
        as_of: "2019-03-06T09:00:00Z",
        tier_one: [
          {
            memory_id: UNBROKEN,
            change: "preference",
            control_writes: "demoted",
            learned_at: "2019-03-05T09:00:00Z",
          },
        ],
        tier_two: [
          {
            memory_id: `${UNBROKEN}2`,
            change: "fast_path_rule",
            evidence: [UNBROKEN],
            promote_ready: false,
            learned_at: "2019-03-05T09:00:00Z",
          },
        ],
        tier_three: [{ memory_id: `${UNBROKEN}3`, department: UNBROKEN, back_to: UNBROKEN }],
        tiers: [{ tier: 1, changes: [UNBROKEN] }],
        learnings_are_not_recorded: false,
        undo_is_not_writable: true,
      },
    },
  },
  // Memory with nobody named asks the API nothing, so it draws no value.
  "/memory": { address: "/memory", signedIn: true, drawsValues: false, answers: {} },
  // One person's memory. The address carries an ordinary reference, because `UNBROKEN` is longer
  // than a principal id may be and the page refuses it before asking, which is correct. The API's
  // own values are unbroken: the reference it echoes is drawn in the card's heading outside any
  // table, a statement may be one unbroken word, and the history table holds a memory id and a
  // diff line inside `.grid__scroll`.
  "/memory/:subject": {
    address: "/memory/u_subject",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/memory": {
        subject_id: UNBROKEN,
        curated: [
          {
            memory_id: UNBROKEN,
            statement: UNBROKEN,
            confidence: 0.9,
            formed_at: "2019-03-05T09:00:00Z",
          },
        ],
        extracted: [],
        history: [
          {
            memory_id: UNBROKEN,
            replaced_id: `${UNBROKEN}0`,
            at: "2019-03-05T09:00:00Z",
            diff: [`+${UNBROKEN}`],
            trigger: null,
            correction: null,
          },
        ],
        considered_per_kind: 200,
        staleness: null,
        corrections_are_not_recorded: false,
        edit_is_not_writable: true,
      },
    },
  },
  // Sessions and sign-in links. Every identifier is in the table, which scrolls, and the served
  // sentences are outside it, where they must wrap. No control is pressed here: the confirmation
  // panel is held to the same rules in `tests/sessions-page.test.tsx` and
  // `tests/sign-in-links-page.test.tsx`.
  "/sessions": {
    address: "/sessions",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/sessions": SESSIONS },
  },
  "/sign-in-links": {
    address: "/sign-in-links",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/sign-ins": SIGN_IN_LINKS },
  },
  // Audit. The actor is drawn twice, in the table and as an option in the Who filter, and the
  // option is the one outside anything that scrolls. The history card is not opened here; it is
  // the same table shape and is held in `tests/audit-page.test.tsx`.
  "/audit": {
    address: "/audit",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/audit": AUDIT },
  },
  "/runs": {
    address: "/runs",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/operate/runs": LIVE_RUNS },
  },
  "/models": {
    address: "/models",
    signedIn: true,
    drawsValues: true,
    answers: MODELS_AND_HEALTH,
  },
  // Questions and gaps. Nothing connected, so the one-row table is drawn. The sentence every asker
  // receives arrives unbroken twice: inside the table, whose parent scrolls, and in the note that
  // quotes the not-found sentence outside it, which has to be able to break.
  "/questions": {
    address: "/questions",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/questions": {
        nothing_connected: true,
        answered_when_nothing_connected: UNBROKEN,
        answered_when_nothing_found: UNBROKEN,
        unanswered_are_recorded: false,
      },
    },
  },
  // Usage and cost. A department and a person are both identifiers with no break in them, one in
  // each table, and every measure is named as not measured so every card on the page is drawn.
  "/usage": {
    address: "/usage",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/usage": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        departments: [{ department: UNBROKEN, questions: 3, people: 1 }],
        people: [{ person: UNBROKEN, questions: 3 }],
        questions: 3,
        machine_included: false,
        not_measured: ["tokens", "model", "agent"],
      },
    },
  },
  // Quality and canaries. A run state the console has no words for is drawn as the API sent it,
  // so an unbroken one reaches the figures list outside any table, which is the `.fields__row`
  // shape that once took a page to 911 pixels.
  "/quality": {
    address: "/quality",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/quality": {
        last_canary_run: {
          started_at: "2019-03-05T06:00:00Z",
          finished_at: "2019-03-05T06:02:00Z",
          state: UNBROKEN,
        },
        canaries_started: false,
        canary_interval_seconds: 43200,
        findings_are_recorded: false,
        evaluation_runs_are_recorded: false,
      },
    },
  },
  // Departments and teams, Access review, Elevation and Subscribers. The review and the
  // subscribers are tables, which scroll; the organisation, the landing, the filter options and
  // every served sentence are outside a table, where they must wrap. No control is pressed here:
  // the confirmation panel is held to the same rules in `tests/govern-people-pages.test.tsx`.
  "/departments": {
    address: "/departments",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/departments": DEPARTMENTS },
  },
  "/access_review": {
    address: "/access_review",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/access-review": ACCESS_REVIEW },
  },
  "/elevation": {
    address: "/elevation",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/elevation": ELEVATION },
  },
  "/subscribers": {
    address: "/subscribers",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/subscribers": SUBSCRIBERS },
  },
  // Artifacts. The identifiers are in the table, which scrolls; the kept rule and the hint are
  // sentences outside it and must wrap. The unread state is a sentence too and is held in
  // `tests/artifacts-page.test.tsx`.
  "/artifacts": {
    address: "/artifacts",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/artifacts": {
        artifacts: [
          {
            artifact_id: UNBROKEN,
            kind: "report",
            agent_id: UNBROKEN,
            produced_for: UNBROKEN,
            produced_at: "2019-03-04T09:00:00Z",
            state: "current",
            superseded_by: "",
            run_id: UNBROKEN,
            agent_version: "3",
            kept_as: "payload",
            kept_until: "2019-04-03T09:00:00Z",
            kept_because: UNBROKEN,
          },
        ],
        unread: "",
        kept_rule: UNBROKEN,
      },
    },
  },
  // Retention and erasure. A store name and a queue reason sit in the table; the served sentences,
  // a cited hold and a finding sit outside it and must wrap. No control is pressed here: the
  // confirmations are held in `tests/retention-page.test.tsx`.
  "/retention": {
    address: "/retention",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/retention": {
        report: {
          report_id: RUNG_ID,
          at: "2019-03-04T09:00:00Z",
          report_only: true,
          complete: true,
          failure: null,
          released: false,
          removed: 0,
          removed_by_class: [],
          held_by_class: [],
          queued_by_class: [],
          stores: [
            {
              store: UNBROKEN,
              data_class: "metadata_ledger",
              lifetime: "fixed_window",
              days: 1825,
              reached: true,
              beyond_horizon: 1,
              held: 0,
              due: 1,
              removed: 0,
              queued: 0,
              queued_because: UNBROKEN,
              unreached_because: "",
              oldest_days: 2000,
            },
          ],
          holds: [{ hold_id: UNBROKEN, reason_code: "litigation", company_wide: false }],
          findings: [UNBROKEN],
        },
      },
      "/api/v1/govern/retention/controls": {
        may_release: true,
        may_hold: true,
        releasing: UNBROKEN,
        withdrawing: UNBROKEN,
        holding: UNBROKEN,
        lifting: UNBROKEN,
        exports: UNBROKEN,
        erasures: UNBROKEN,
        kept: [{ data_class: UNBROKEN, lifetime: "fixed_window", days: 30, because: UNBROKEN }],
      },
    },
  },
  // My workspace. An agent id and an item id sit in tables that scroll; a memory statement, the
  // disclosure line and every served sentence sit outside them and must wrap.
  "/me": {
    address: "/me",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/me/workspace": {
        principal_id: UNBROKEN,
        display_name: UNBROKEN,
        asked: { since: "2019-03-01T00:00:00Z", questions: 3, corrections: UNBROKEN },
        agents: [{ agent_id: UNBROKEN, provision: "provided", channels: [UNBROKEN], uses: 2 }],
        agents_used_since: "2019-02-05T00:00:00Z",
        budget: [
          {
            period: "month",
            ceiling_minor: 4000,
            spent_minor: 1000,
            headroom_minor: 3000,
            alerts_crossed: [],
          },
        ],
        budget_unread: "",
        knowledge: [{ item_id: UNBROKEN, level: "department", department: UNBROKEN }],
        knowledge_truncated: false,
        knowledge_not_shown: UNBROKEN,
        learned: [
          {
            memory_id: "m_1",
            statement: UNBROKEN,
            stated: true,
            confidence: 1,
            formed_at: "2019-02-28T00:00:00Z",
          },
        ],
        learned_undo: UNBROKEN,
        can_ask_about: UNBROKEN,
        accounts: UNBROKEN,
        staleness: null,
      },
    },
  },
  // Webhooks. Identifiers are in the tables, which scroll; the served sentences, the vault's state
  // and the findings are outside them, where they must wrap. No control is pressed here: the
  // confirmation panels and the register form are held in `tests/webhooks-page.test.tsx`.
  "/webhooks": {
    address: "/webhooks",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/webhooks": WEBHOOKS },
  },
  // Storage. The bucket table scrolls; the address, the prefix and the sentences wrap.
  "/storage": {
    address: "/storage",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/storage": STORAGE },
  },
  // Import and export. The catalogue and the exports tables scroll; the served sentences and the
  // export form sit outside them. The confirmation is held in `tests/data-transfer-page.test.tsx`.
  "/import-export": {
    address: "/import-export",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/data-transfer": DATA_TRANSFER },
  },
  "/*": { address: "/no/such/page", signedIn: true, drawsValues: false, answers: {} },
  [CALLBACK_PATH]: {
    address: `${CALLBACK_PATH}?code=X&state=Y`,
    signedIn: false,
    drawsValues: false,
    answers: {},
  },
  [SIGNED_OUT_PATH]: { address: SIGNED_OUT_PATH, signedIn: false, drawsValues: false, answers: {} },
  [FIRST_RUN_PATH]: { address: FIRST_RUN_PATH, signedIn: false, drawsValues: false, answers: {} },
};

const SHELL_PATTERNS = Object.keys(PAGES).filter((pattern) => PAGES[pattern]?.signedIn);
const VALUE_PATTERNS = Object.keys(PAGES).filter((pattern) => PAGES[pattern]?.drawsValues);

/** Every split page is transformed once, before anything is timed. */
beforeAll(async () => {
  await import("../src/pages/Records");
  await import("../src/pages/Agent");
  await import("../src/pages/Approvals");
}, 120_000);

/** Every leaf pattern in a route table, spelled from the root. */
function patternsOf(routes: readonly RouteObject[], parent = ""): string[] {
  const found: string[] = [];
  for (const route of routes) {
    const own =
      route.index === true
        ? parent || "/"
        : route.path === undefined
          ? parent
          : route.path.startsWith("/")
            ? route.path
            : `${parent === "/" ? "" : parent}/${route.path}`;
    if (route.children && route.children.length > 0) {
      found.push(...patternsOf(route.children, own));
    } else {
      found.push(own);
    }
  }
  return found;
}

async function mount(pattern: string): Promise<HTMLElement> {
  const page = PAGES[pattern];
  if (page === undefined) {
    throw new Error(`${pattern} has no page case.`);
  }
  const idp = fakeIdentityProvider({
    api(url) {
      const asked = new URL(url, CONSOLE_ORIGIN).pathname;
      if (!(asked in page.answers)) {
        return null;
      }
      return new Response(JSON.stringify(page.answers[asked]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp, path: page.address.split("?")[0] });
  if (page.signedIn) {
    await signIn(loaded);
  }
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [page.address] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(
    () => {
      if (!container.querySelector("h1, .notice")) {
        throw new Error(`${pattern} has not arrived`);
      }
      if (container.querySelector('[role="status"], .grid__busy')) {
        throw new Error(`${pattern} is still asking`);
      }
    },
    { timeout: 20_000 },
  );
  return container;
}

const RULES: readonly OrderedRule[] = consoleRules();

/** The design tokens, so a width written as a token is compared as the length it stands for. */
const TOKENS: Readonly<Record<string, string>> = Object.fromEntries(
  RULES.filter((rule) => rule.selector === ":root" && rule.atRule === "").flatMap((rule) =>
    Object.entries(rule.declarations).filter(([property]) => property.startsWith("--")),
  ),
);

function resolved(value: string | undefined): string {
  return (value ?? "").replace(/var\((--[\w-]+)\)/g, (whole, name: string) => TOKENS[name] ?? whole);
}

function named(element: Element): string {
  const classes = element.getAttribute("class");
  return `${element.tagName.toLowerCase()}${classes ? `.${classes.trim().split(/\s+/).join(".")}` : ""}`;
}

/** Whether an element, or anything holding it, scrolls sideways at this width. */
function insideSidewaysScroll(element: Element, width: number): boolean {
  for (let at: Element | null = element; at !== null; at = at.parentElement) {
    const overflow = declared(at, "overflow-x", RULES, width) ?? declared(at, "overflow", RULES, width);
    if (overflow !== undefined && /\b(auto|scroll)\b/.test(overflow)) {
      return true;
    }
  }
  return false;
}

/** What a browser's own stylesheet does with white space in an element nobody styled. */
function userAgentWhiteSpace(element: Element): string | undefined {
  return element.tagName === "PRE" || element.tagName === "TEXTAREA" ? "pre" : undefined;
}

/** Every text carrying the unbroken value, and the reason it could not break, if it could not. */
function unbrokenValues(container: HTMLElement, width: number): { seen: number; stuck: string[] } {
  const stuck: string[] = [];
  let seen = 0;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const holder = node.parentElement;
    if (holder === null || !(node.textContent ?? "").includes(UNBROKEN)) {
      continue;
    }
    seen += 1;
    if (insideSidewaysScroll(holder, width)) {
      continue;
    }
    const whiteSpace = inherited(holder, "white-space", RULES, width, userAgentWhiteSpace) ?? "normal";
    const wrap = inherited(holder, "overflow-wrap", RULES, width) ?? "normal";
    const wordBreak = inherited(holder, "word-break", RULES, width) ?? "normal";
    const mayWrap = whiteSpace !== "nowrap" && whiteSpace !== "pre";
    const breaksAWord = wrap === "anywhere" || wordBreak === "break-all";
    if (!mayWrap || !breaksAWord) {
      stuck.push(`${named(holder)}: white-space ${whiteSpace}, overflow-wrap ${wrap}`);
    }
  }
  return { seen, stuck };
}

const WIDTH_PROPERTIES = [
  "width",
  "min-width",
  "inline-size",
  "min-inline-size",
  "flex-basis",
  "grid-template-columns",
  "grid-auto-columns",
];

describe("the console's stylesheets at a phone's width", () => {
  test("no stylesheet describes a phone with a max-width query, so the narrow screen is every sheet's base case", () => {
    // What breaks if this is deleted: a desktop layout with a `max-width` query patched over
    // it, which is the shape the shell had, and a phone that is the case the next edit
    // forgets. Every width query in every sheet must be a `min-width` one. The sibling half
    // is that the enhancement exists at all, because a sheet with no queries passes the first
    // half and has no sidebar on any screen.
    const widthQueries = CONSOLE_SHEETS.flatMap((sheet) =>
      parseCss(readConsoleFile(sheet))
        .filter((rule) => /width/.test(rule.atRule))
        .map((rule) => `${sheet} ${rule.atRule}`),
    );

    expect(widthQueries.filter((query) => !/ @media \(min-width: [^)]+\)$/.test(query))).toEqual([]);
    expect(widthQueries).toEqual(
      expect.arrayContaining([
        "src/styles/app.css @media (min-width: 48rem)",
        "src/styles/approvals.css @media (min-width: 64rem)",
        "src/styles/agent-workspace.css @media (min-width: 60rem)",
      ]),
    );
  });

  test("no width a phone applies is wider than the phone", () => {
    // What breaks if this is deleted: a `min-width: 24rem` on a card or a sidebar 15rem wide
    // beside the page, applied at every width, and a page that scrolls sideways while looking
    // right on the screen it was written on. A token is compared as the length it stands for.
    const checked: string[] = [];
    for (const rule of RULES) {
      if (!appliesAt(rule.atRule, PHONE_PX)) {
        continue;
      }
      for (const property of WIDTH_PROPERTIES) {
        const value = rule.declarations[property];
        if (value === undefined) {
          continue;
        }
        checked.push(`${rule.selector} ${property}`);
        for (const length of resolved(value).matchAll(/-?\d*\.?\d+(?:px|rem|em)\b/g)) {
          expect(pixels(length[0]) ?? 0, `${rule.selector} { ${property}: ${value} }`).toBeLessThanOrEqual(PHONE_PX);
        }
      }
    }
    // A reader that found no width declarations at all would pass the loop for nothing.
    expect(checked).toEqual(expect.arrayContaining([".approval-list grid-template-columns", ".form-control width"]));
  });
});

describe("every registered page at a phone's width", () => {
  test("every route the console registers has a page case here", async () => {
    // What breaks if this is deleted: a page added to `App.tsx` that nobody held to a phone,
    // because the tests below loop over a list somebody typed. The list is compared with the
    // route table itself, both ways, so a stale entry fails as loudly as a missing one.
    await loadConsole();
    const { routes } = await import("../src/App");

    expect(patternsOf(routes).sort()).toEqual(Object.keys(PAGES).sort());
  });

  test.each(SHELL_PATTERNS)(
    "%s puts the whole navigation above the page, every link a thumb tall",
    async (pattern) => {
      // What breaks if this is deleted: a 240 pixel sidebar beside 120 pixels of page, a menu
      // hidden on a phone with nothing to open it, or links a cursor can hit and a thumb cannot.
      // The navigation must precede the page, must not be hidden, must stack above it rather
      // than beside it, and must list every section the route table has, which is every
      // pattern under the shell without a parameter.
      const container = await mount(pattern);
      const body = container.querySelector(".shell__body");
      const nav = container.querySelector("nav.shell__nav");
      const main = container.querySelector("main");
      expect(body).not.toBeNull();
      expect(nav).not.toBeNull();
      expect(main).not.toBeNull();

      expect(declared(body as Element, "flex-direction", RULES, PHONE_PX)).toBe("column");
      expect((nav as Element).compareDocumentPosition(main as Element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      for (let at: Element | null = nav; at !== null; at = at.parentElement) {
        expect(declared(at, "display", RULES, PHONE_PX), named(at)).not.toBe("none");
        expect(declared(at, "visibility", RULES, PHONE_PX), named(at)).not.toBe("hidden");
      }

      const links = [...(nav as Element).querySelectorAll("a")];
      const sections = SHELL_PATTERNS.filter((one) => !one.includes(":") && !one.includes("*"));
      expect(links.map((link) => link.getAttribute("href")).sort()).toEqual([...sections].sort());
      for (const link of links) {
        const height = pixels(resolved(declared(link, "min-height", RULES, PHONE_PX)));
        expect(height ?? 0, link.getAttribute("href") ?? "").toBeGreaterThanOrEqual(TAP_TARGET_PX);
        expect(declared(link, "display", RULES, PHONE_PX)).toMatch(/^(block|flex|inline-flex|inline-block)$/);
      }
    },
  );

  test.each(VALUE_PATTERNS)("%s lets every value the API sent break inside the screen", async (pattern) => {
    // What breaks if this is deleted: an identifier with no space in it pushing the page past
    // the edge of the screen, which is what the overview and the agent workspace did at 911
    // pixels. Every text carrying the unbroken value must either sit inside something that
    // scrolls sideways, which is the grid's decision, or be allowed to wrap and to break inside
    // a word. `overflow-wrap: break-word` is not accepted, because it does not shrink a flex
    // item's smallest size and that is exactly the case that overflowed. The count proves the
    // value reached the page, so a page that drew nothing cannot pass.
    const container = await mount(pattern);
    const found = unbrokenValues(container, PHONE_PX);

    expect(found.seen).toBeGreaterThan(0);
    expect(found.stuck).toEqual([]);
  });

  test("a grid keeps an identifier whole and scrolls instead, so the body's breaking rule stops at the table", async () => {
    // What breaks if this is deleted: the one exception to `overflow-wrap: anywhere` going
    // quietly, after which every column shrinks below its identifiers, a grid never scrolls,
    // and each identifier is split across lines. The value test above passes either way,
    // because a value inside a scrolling container is exempt, so this sibling holds the
    // exception itself: the cell's text does not break, and it sits inside what scrolls.
    const container = await mount("/records/:entity");
    const cells = [...container.querySelectorAll(".grid__table td")].filter((cell) =>
      (cell.textContent ?? "").includes(UNBROKEN),
    );

    expect(cells.length).toBeGreaterThan(0);
    for (const cell of cells) {
      expect(inherited(cell, "overflow-wrap", RULES, PHONE_PX)).toBe("normal");
      expect(insideSidewaysScroll(cell, PHONE_PX)).toBe(true);
    }
  });

  test("a wider screen still gets the sidebar and the label column, so the phone rules are a base and not the whole", async () => {
    // What breaks if this is deleted: every assertion above is satisfied by deleting the
    // desktop layout, or by a reader that ignores media queries. At 1280 pixels the shell is a
    // row with a sidebar of the token's width and the label column is back, and at 360 neither
    // is, which also proves the cascade reader applies a query only where it matches.
    const container = await mount("/");
    const body = container.querySelector(".shell__body") as Element;
    const nav = container.querySelector("nav.shell__nav") as Element;
    const row = container.querySelector(".fields__row") as Element;
    const label = row.querySelector("dt") as Element;

    expect(declared(body, "flex-direction", RULES, WIDE_PX)).toBe("row");
    expect(pixels(resolved(declared(nav, "width", RULES, WIDE_PX)))).toBeGreaterThan(PHONE_PX / 2);
    expect(declared(nav, "width", RULES, PHONE_PX)).toBeUndefined();
    expect(declared(row, "flex-direction", RULES, WIDE_PX)).toBe("row");
    expect(declared(row, "flex-direction", RULES, PHONE_PX)).toBe("column");
    expect(pixels(resolved(declared(label, "width", RULES, WIDE_PX)))).toBeGreaterThan(0);
    expect(declared(label, "width", RULES, PHONE_PX)).toBeUndefined();
  });
});
