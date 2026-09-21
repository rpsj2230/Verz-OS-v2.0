/**
 * Every page the console registers, the address it is mounted at, and what the stand-in API answers
 * it with.
 *
 * Written once and read by several tests. `tests/phone-width.test.tsx` holds every page to a phone's
 * width with these answers, and `tests/screen-states.test.tsx` mounts the same pages in the four
 * states a request can leave them in, answering the empty state with these same bodies with every
 * list emptied. Two copies would be two sets of fixtures that drift, and the drift would be
 * invisible: a page whose answer shape changed would be fixed in one test and go on passing in the
 * other against a body the API no longer sends.
 *
 * The values are identifier-shaped tokens with nowhere to break, because that is what the phone
 * test needs, and the state test does not care what the values are.
 *
 * Task ids: none
 */

import { CALLBACK_PATH, SIGNED_OUT_PATH } from "../../src/auth/constants";
import { RETURN_PATH as STAFF_LIST_RETURN_PATH } from "../../src/setup/staffList";
import { FIRST_RUN_PATH } from "../../src/setup/wizard";
import { NAVIGATION_ADDRESS, departmentConsole } from "./navigation";

/** A value with nowhere to break, which is what an identifier from the API usually is. */
export const UNBROKEN = `UNBROKEN${"x".repeat(72)}`;

export const RUNG_ID = "11111111-1111-4111-8111-111111111111";

export interface PageCase {
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

/**
 * The matrix gate's two answers on the Routing screen: one held change with its failing case, and
 * one golden question, whose question, asker and case id are tokens with nowhere to break.
 */
const ROUTING_CHANGES = {
  items: [
    {
      id: "22222222-2222-4222-8222-222222222222",
      kind: "edit",
      status: "held",
      rung_id: RUNG_ID,
      proposed: {},
      failing: [{ case: UNBROKEN, reason: UNBROKEN }],
      reasons: [UNBROKEN],
      quality_share: 0.5,
      proposed_by: UNBROKEN,
      decided_at: "2019-03-04T09:00:00Z",
      rung: null,
    },
  ],
};

const GOLDEN_QUESTIONS = {
  items: [
    {
      id: "33333333-3333-4333-8333-333333333333",
      question: UNBROKEN,
      asked_as: UNBROKEN,
      expect: "refuse",
      created_by: UNBROKEN,
    },
  ],
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
  // The profile's tier and pinned model (M5.7.3), drawn on the Profile pane.
  profile: { tier: "main", model_pin_provider: null, model_pin_model: null },
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

/** One page of people, whose subject key and capability are both unbreakable tokens. */
const PEOPLE = {
  items: [{ subject: `principal:${UNBROKEN}`, capabilities: [UNBROKEN] }],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
  staleness: null,
};

/**
 * The People screen's Data steward card with nobody appointed, so its form is drawn. Sentences
 * rather than tokens, because the card draws the API's sentences and never an identifier.
 */
const NO_STEWARD = {
  appointed: false,
  principal_id: null,
  display_name: null,
  told: "No data steward is appointed.",
  appointing_another: "They are granted the reads of every connected source.",
  appointing_yourself: "Your account then holds both.",
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
  how_to_choose: UNBROKEN,
};

/**
 * One guide for connecting a staff source, whose title, steps and help are unbreakable tokens.
 * The form is drawn, because the reader may connect, so the forms test opens it.
 */
const STAFF_SOURCE_GUIDES = {
  guides: [
    {
      source: "lark",
      title: UNBROKEN,
      where: UNBROKEN,
      steps: [UNBROKEN],
      fields: [
        { key: "location", label: "Platform", help: UNBROKEN, secret: false, example: "larksuite.com" },
        { key: "app_id", label: "App ID", help: UNBROKEN, secret: false, example: "cli_a" },
        { key: "app_secret", label: "App Secret", help: UNBROKEN, secret: true, example: "" },
      ],
      connectable: true,
      unavailable: "",
      chosen: true,
    },
  ],
  may_connect: true,
  schedule: UNBROKEN,
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
  next_cursor: null,
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
  next_cursor: null,
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
      },
    ],
    exhausted_tiers: ["main"],
    editable: true,
    vault: "ready",
    vault_told: "The secrets vault answered.",
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
  items: [
    {
      slug: UNBROKEN,
      name: UNBROKEN,
      teams: [
        {
          slug: UNBROKEN,
          name: UNBROKEN,
          members: [{ principal_id: `${UNBROKEN}1`, display_name: UNBROKEN, disabled: false }],
        },
      ],
      members: [
        { principal_id: UNBROKEN, display_name: UNBROKEN, disabled: true },
        { principal_id: `${UNBROKEN}2`, display_name: UNBROKEN, disabled: false },
      ],
      lead: { principal_id: `${UNBROKEN}1`, display_name: UNBROKEN, disabled: false },
    },
  ],
  next_cursor: null,
  unplaced: [{ principal_id: `${UNBROKEN}0`, display_name: UNBROKEN, disabled: false, department: UNBROKEN }],
  truncated: true,
  may_organise: true,
  staleness: null,
  teams: UNBROKEN,
  leads: UNBROKEN,
  counted: UNBROKEN,
  organising: UNBROKEN,
};

const ELEVATION = {
  prompt: UNBROKEN,
  holds_nothing_standing: false,
  may_authorise: true,
  reasons: [UNBROKEN],
  longest_hours: 4,
  items: [
    {
      request_id: UNBROKEN,
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      capability: UNBROKEN,
      scope_slug: UNBROKEN,
      reason: UNBROKEN,
      explanation: UNBROKEN,
      hours: 2,
      requested_at: "2019-03-04T09:00:00Z",
      state: "pending",
      decided_by: null,
      decided_at: null,
      lapses_at: null,
      decidable: true,
    },
  ],
  next_cursor: null,
  truncated: true,
  what: UNBROKEN,
  recorded: UNBROKEN,
  notified: UNBROKEN,
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
  next_cursor: null,
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
  library: [],
  library_truncated: false,
  agents: [],
  may_add: false,
  registry_is_absent: false,
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
          next_attempt_at: "2019-03-04T09:05:00Z",
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
  dispatcher: {
    runs_here: true,
    paused: false,
    last_started_at: "2019-03-04T09:00:00Z",
    last_finished_at: "2019-03-04T09:00:01Z",
    last_outcome: "ok",
    last_report: UNBROKEN,
    told: UNBROKEN,
  },
  inbound: {
    channels: [
      { channel: "slack", verification: "written", check: `brain.channels.${UNBROKEN}:verify`, how: UNBROKEN },
      { channel: "lark", verification: "not_written", check: "", how: UNBROKEN },
    ],
    channels_told: UNBROKEN,
    automation_path: `/api/v1/${UNBROKEN}`,
    automation_told: UNBROKEN,
  },
  registering: UNBROKEN,
  replacing: UNBROKEN,
  switching_off: UNBROKEN,
  secret_minimum: 32,
};

const NOTIFICATIONS = {
  notices: [
    {
      kind: "reverification_request",
      title: UNBROKEN,
      told: UNBROKEN,
      about: UNBROKEN,
      how: UNBROKEN,
      sent: true,
      switchable: true,
      fixed_because: "",
      on: false,
      changed_by: UNBROKEN,
      changed_at: "2019-03-04T09:00:00Z",
    },
    {
      kind: "emergency_access",
      title: UNBROKEN,
      told: UNBROKEN,
      about: UNBROKEN,
      how: UNBROKEN,
      sent: false,
      switchable: false,
      fixed_because: UNBROKEN,
      on: true,
      changed_by: null,
      changed_at: null,
    },
  ],
  email: {
    configured: true,
    host: `${UNBROKEN}.example.test`,
    port: 587,
    security: "starttls",
    sender: `${UNBROKEN}@example.test`,
    username: UNBROKEN,
    changed_by: UNBROKEN,
    changed_at: "2019-03-04T09:00:00Z",
    password: { held: null, written_at: null, vault: "unreachable", vault_told: UNBROKEN },
  },
  securities: ["starttls", "tls"],
  email_used_for: UNBROKEN,
  subscribers: UNBROKEN,
  ships_on: UNBROKEN,
  only_the_last_change_is_kept: UNBROKEN,
  switching_off: UNBROKEN,
  switching_on: UNBROKEN,
  saving_email: UNBROKEN,
  keeping_password: UNBROKEN,
  sending_trial: UNBROKEN,
  plain_smtp_refused: UNBROKEN,
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

const VAULT_SLOT = {
  slot: UNBROKEN,
  description: UNBROKEN,
  state: "held",
  set_at: "2019-03-04T09:00:00Z",
  request: [UNBROKEN],
  refuse: [UNBROKEN],
};

const VAULT = {
  seal: "open",
  told: UNBROKEN,
  slots_unread: "",
  providers: [VAULT_SLOT],
  connectors: [VAULT_SLOT],
  leases: [{ connector: UNBROKEN, issued: 3, revoked: 2, expired: 1, not_revoked: 0 }],
  leases_told: UNBROKEN,
  lease_ttl_minutes: 15,
  rotation: UNBROKEN,
  audit: { entries: 4, refused: 1, last_shipped_at: "2019-03-04T09:00:00Z", told: UNBROKEN },
  token_policy: "own",
  token_policies: [UNBROKEN],
  token_told: UNBROKEN,
};

const REQUIREMENT_CHECKS = {
  areas: [
    { area: "Permissions", proves: "M1.8.8", requirements: 2, passed: 1, failed: 0, unchecked: 1 },
    { area: "Models", proves: "M5.6.5", requirements: 1, passed: 0, failed: 0, unchecked: 1 },
  ],
  area: "Permissions",
  requirements: [
    {
      id: "ARC-A-001",
      requirement: UNBROKEN,
      source: UNBROKEN,
      latest: {
        requirement_id: "ARC-A-001",
        outcome: "passed",
        checked_by: "u_admin",
        checked_at: "2019-03-04T09:00:00Z",
        release_commit: "a".repeat(40),
        note: UNBROKEN,
      },
    },
    { id: "DEC-30", requirement: UNBROKEN, source: UNBROKEN, latest: null },
  ],
  release_commit: "a".repeat(40),
  told: UNBROKEN,
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

export const PAGES: Readonly<Record<string, PageCase>> = {
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
      // The install card: the four parts `brain.readiness` always names, at the API's root.
      "/health/ready": {
        status: "ok",
        commit: UNBROKEN,
        checks: { database: true },
        reported: { sign_in: true },
        parts: [
          { name: "database", state: "ready", gates: true },
          { name: "cache", state: "not_configured", gates: false },
          { name: "vault", state: "not_configured", gates: false },
          { name: "sign_in", state: "ready", gates: false },
        ],
      },
    },
  },
  // Department, SCREEN 2's overview, mounted as a department admin would open it: the stand-in API
  // gives a department's console, so the menu drawn above it is that console's and not the
  // company's, and the department's name is an unbroken value in the header and on the page. The
  // three cards each draw a value the API sent: a count, an agent's name, and the sentence every
  // asker is told.
  "/department": {
    address: "/department",
    signedIn: true,
    drawsValues: true,
    answers: {
      [NAVIGATION_ADDRESS]: departmentConsole(UNBROKEN),
      "/api/v1/report/usage": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        departments: [{ department: UNBROKEN, questions: 3, people: 1 }],
        people: [{ person: UNBROKEN, questions: 3 }],
        questions: 3,
        machine_included: false,
        not_measured: [],
        tokens: [
          {
            axis: "model",
            lines: [{ key: UNBROKEN, runs: 3, tokens_in: 1200, tokens_out: 300 }],
            total_runs: 3,
            total_tokens_in: 1200,
            total_tokens_out: 300,
          },
        ],
      },
      "/api/v1/agents": {
        items: [{ agent_id: "quote-helper", display_name: UNBROKEN, owner_id: UNBROKEN }],
        next_cursor: null,
        truncated: false,
      },
      "/api/v1/report/questions": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [],
        nothing_connected: true,
        answered_when_nothing_connected: UNBROKEN,
        answered_when_nothing_found: UNBROKEN,
        unanswered_are_recorded: false,
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
    answers: {
      "/api/v1/routing/rungs": MATRIX,
      "/api/v1/routing/changes": ROUTING_CHANGES,
      "/api/v1/routing/golden-questions": GOLDEN_QUESTIONS,
    },
  },
  "/routing/:rungId": {
    address: `/routing/${RUNG_ID}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/routing/rungs": MATRIX,
      "/api/v1/routing/changes": ROUTING_CHANGES,
      "/api/v1/routing/golden-questions": GOLDEN_QUESTIONS,
    },
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
        next_cursor: null,
        truncated: false,
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
  // The Automations tab, so the gallery and the installed automations it draws are held to a phone
  // as well as the workspace.
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
      "/api/v1/agents/quote-helper/automations": AGENT_AUTOMATIONS,
    },
  },
  "/approvals": {
    address: "/approvals",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/approvals": { items: [card("sus_1")], next_cursor: null, truncated: false } },
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
    answers: { "/api/v1/govern/people": PEOPLE, "/api/v1/govern/data-steward": NO_STEWARD },
  },
  "/people/:subject": {
    address: `/people/${encodeURIComponent(`principal:${UNBROKEN}`)}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/people": PEOPLE,
      "/api/v1/govern/scopes": SCOPES,
      "/api/v1/govern/data-steward": NO_STEWARD,
      "/api/v1/govern/packs": { packs: [{ slug: "helpdesk", label: UNBROKEN, capabilities: [UNBROKEN] }] },
    },
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
      "/api/v1/govern/roles/holders": {
        items: [{ id: "g-1", principal_id: UNBROKEN, role: "auditor", deputy_of: null, not_after: null }],
        editable: true,
      },
      "/api/v1/govern/roles/misconfigurations": {
        items: [{ principal_id: "u_2", kind: "role_without_capability", sentence: UNBROKEN }],
      },
      "/api/v1/govern/roles/group-rules": {
        rules: [
          {
            id: "r-1",
            idp_group: UNBROKEN,
            role: "auditor",
            scope: null,
            created_by: UNBROKEN,
            created_at: "2019-03-04T09:00:00Z",
          },
        ],
        synced: [
          {
            principal_id: UNBROKEN,
            role: "auditor",
            source_group: UNBROKEN,
            first_seen_at: "2019-03-04T09:00:00Z",
            last_seen_at: "2019-03-04T09:00:00Z",
          },
        ],
        editable: true,
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
    answers: {
      "/api/v1/govern/staff_sources": STAFF_SOURCES,
      "/api/v1/govern/staff_sources/guides": STAFF_SOURCE_GUIDES,
      // The nightly sync's three reads, each carrying the unbroken token where a value is drawn.
      "/api/v1/govern/staff_sources/runs": {
        runs: [
          {
            source: UNBROKEN,
            started_at: "2999-03-02T02:00:00Z",
            finished_at: "2999-03-02T02:00:05Z",
            outcome: UNBROKEN,
            detail: UNBROKEN,
            added: [UNBROKEN],
            marked_left: [],
            renamed: [],
            withheld: [],
            changed_nobody: false,
          },
        ],
      },
      "/api/v1/govern/staff_sources/credential": {
        slot: "connector_keys/staff_source",
        held: true,
        set_at: null,
        vault: "ready",
        told: "The secrets vault answered.",
        form: UNBROKEN,
      },
      "/api/v1/govern/staff_sources/transfers": {
        transfers: [{ agent_id: UNBROKEN, display_name: UNBROKEN, owner_id: UNBROKEN, running: false }],
      },
    },
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
  // Installation settings and the leaving card. The branding value is drawn in a field, so the
  // unbroken value is the non-editable one and the handover step's sentence.
  "/settings": {
    address: "/settings",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/settings": {
        groups: [
          {
            group: "storage",
            title: "Storage",
            editable: false,
            changed_elsewhere: UNBROKEN,
            settings: [
              {
                name: "INSTALL_OBJECT_STORE_URL",
                meaning: UNBROKEN,
                value: UNBROKEN,
                source: "environment",
                default: "",
                required: false,
                editable: false,
                applies: UNBROKEN,
                read_by: ["brain.ops.object_store"],
              },
            ],
          },
        ],
        findings: [],
        profile: UNBROKEN,
        starter: {
          roles: ["member"],
          packs: ["starter"],
          scopes: ["company"],
          furnished: true,
          agent_templates: [],
          agents_installed: false,
          agents_told: UNBROKEN,
        },
        credentials: UNBROKEN,
        editable_because: UNBROKEN,
        leaving: {
          told: UNBROKEN,
          steps: [{ what: "audit", kind: "store", holds: UNBROKEN, by: "command", how: UNBROKEN }],
          backup_retention_days: 35,
          procedure: "docs/install/handover.md",
          commands: ["python -m brain.ops.handover_run certify <dir>"],
        },
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
        every_change_is_in_the_audit_trail: true,
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
  // Logs. The event, the place, the reference, the exception and a field's name and value are all
  // strings from the API, and none of them has anywhere to break.
  "/logs": {
    address: "/logs",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/logs": {
        start: "2019-03-05T09:00:00Z",
        end: "2019-03-06T09:00:00Z",
        items: [
          {
            at: "2019-03-06T08:30:00Z",
            last_at: "2019-03-06T08:31:00Z",
            level: "warning",
            event: UNBROKEN,
            origin: UNBROKEN,
            reference: UNBROKEN,
            error_type: UNBROKEN,
            repeats: 3,
            fields: { [UNBROKEN]: UNBROKEN },
          },
        ],
        next_cursor: UNBROKEN,
        kept_for_days: 30,
        debug_is_not_kept: true,
        info_is_a_sample: true,
        worker_output_is_not_kept: true,
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
        every_change_is_in_the_audit_trail: true,
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
        every_change_is_in_the_audit_trail: true,
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
  // side of a phone before `.grid__scroll` existed. The connect card draws a select, and the
  // sources connected at the server draw sentences whose labels are identifiers too. The unread
  // and failure states draw a notice and are held in `tests/connectors-page.test.tsx` instead,
  // for the recovery case's reason.
  "/connectors": {
    address: "/connectors",
    signedIn: true,
    drawsValues: true,
    answers: {
      // Connect Lark's guide, every drawn value the unbroken token.
      "/api/v1/connectors/lark-app": {
        uses: [
          {
            name: "staff_list",
            label: UNBROKEN,
            what: UNBROKEN,
            scopes: [],
            switched_on: true,
            key_held: true,
            status: UNBROKEN,
            may_switch_on: true,
          },
        ],
        chosen: ["staff_list"],
        steps: [{ title: UNBROKEN, text: UNBROKEN }],
        scopes: [{ name: UNBROKEN, what: UNBROKEN, read_only: true }],
        platforms: ["larksuite.com"],
        platform: "larksuite.com",
        base: "",
        developer_console: "https://open.larksuite.com/app",
        events_address: "",
        channel_note: UNBROKEN,
        knowledge_note: UNBROKEN,
        test_note: UNBROKEN,
        staff_sources_screen: "/staff_sources",
        vault_told: "",
      },
      "/api/v1/connectors": {
        connectors: [
          {
            name: UNBROKEN,
            connected_by: UNBROKEN,
            connected_at: "2019-03-04T09:00:00Z",
            key_held: true,
            key_written_at: "2019-03-04T09:00:05Z",
            pinned: true,
            declaration: UNBROKEN,
            may_disconnect: true,
            last_synced_at: "2019-03-04T09:00:00Z",
            next_sync_at: "2019-03-04T10:00:00Z",
            sync: UNBROKEN,
            trust: {
              name: UNBROKEN,
              wiring: "rest",
              credential: `Held in the vault since it was connected. ${UNBROKEN}`,
              budget: `60 requests a minute. ${UNBROKEN}`,
              projected_fields: 9,
              checked_at: "2019-03-04T09:00:00Z",
              health: "ok",
              lifecycle: "registered",
              serving: false,
              version: "1.0.0",
              reaches: `Reaches view ${UNBROKEN}, and nothing else in the source.`,
              access: UNBROKEN,
              permission_sync: UNBROKEN,
            },
          },
        ],
        unread: "",
        connecting: UNBROKEN,
        confirm_connect: UNBROKEN,
        confirm_disconnect: UNBROKEN,
        copy_policy: [{ what: UNBROKEN, verdict: "projected", why: UNBROKEN }],
        budget_unread: UNBROKEN,
        may_connect: true,
        vault: "ready",
        vault_told: "",
        connectable: [
          {
            name: UNBROKEN,
            label: UNBROKEN,
            settings: [{ name: "tenant_id", label: UNBROKEN, hint: UNBROKEN, max_chars: 200, blank: `Give the ${UNBROKEN}.` }],
            credential_label: UNBROKEN,
            credential_hint: UNBROKEN,
            may_connect: true,
          },
        ],
        not_connectable: [{ name: UNBROKEN, label: UNBROKEN, why: UNBROKEN }],
        evidence: [
          {
            name: UNBROKEN,
            label: UNBROKEN,
            recorded: UNBROKEN,
            credential: UNBROKEN,
            live_read: UNBROKEN,
            last_read_live_at: null,
          },
        ],
        key_max_chars: 1000,
        key_blank: "Paste the key the source issued for this connection.",
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
            in_effect: true,
            undo_offered: true,
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
        considered: 500,
        undo_says: { demoted: UNBROKEN, superseded: UNBROKEN },
        staleness: null,
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
  // Questions and gaps. Nothing connected, so the one-row table is drawn, and one gap line, so the
  // second is. The sentence every asker receives arrives unbroken twice: inside the table, whose
  // parent scrolls, and in the note that quotes the not-found sentence outside it, which has to be
  // able to break. The gap line's department and source are unbroken inside their own table.
  "/questions": {
    address: "/questions",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/questions": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [{ department: UNBROKEN, source: UNBROKEN, asked: 3 }],
        nothing_connected: true,
        answered_when_nothing_connected: UNBROKEN,
        answered_when_nothing_found: UNBROKEN,
        unanswered_are_recorded: false,
      },
    },
  },
  // Usage and cost. A department and a person are both identifiers with no break in them, one in
  // each table, and a model name is one too, in the token table the API sends in place of the
  // not-measured sentences it used to.
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
        not_measured: [],
        tokens: [
          {
            axis: "model",
            lines: [{ key: UNBROKEN, runs: 3, tokens_in: 1200, tokens_out: 300 }],
            total_runs: 3,
            total_tokens_in: 1200,
            total_tokens_out: 300,
          },
        ],
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
        canaries_owed: false,
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
  "/access-requests": {
    address: "/access-requests",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/access-requests": {
        items: [
          {
            request_id: UNBROKEN,
            asker_id: UNBROKEN,
            subject: UNBROKEN,
            question: UNBROKEN,
            requested_capability: UNBROKEN,
            requested_at: "2019-03-04T09:00:00Z",
          },
        ],
        next_cursor: null,
        total: null,
        truncated: true,
      },
    },
  },
  "/elevation": {
    address: "/elevation",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/elevation": ELEVATION,
      "/api/v1/govern/elevation/notices": {
        items: [
          {
            session_id: "s-1",
            principal_id: UNBROKEN,
            authorised_by: UNBROKEN,
            reason: "lockout",
            lapses_at: "2019-03-04T13:00:00Z",
            told_at: "2019-03-04T09:00:00Z",
          },
        ],
      },
    },
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
        may_erase: true,
        may_read_exports: true,
        releasing: UNBROKEN,
        withdrawing: UNBROKEN,
        holding: UNBROKEN,
        lifting: UNBROKEN,
        erasing: UNBROKEN,
        exports: UNBROKEN,
        erasures: UNBROKEN,
        exports_not_yours: UNBROKEN,
        kept: [{ data_class: UNBROKEN, lifetime: "fixed_window", days: 30, because: UNBROKEN }],
      },
      "/api/v1/govern/erasures": {
        requests: [
          {
            request_id: RUNG_ID,
            subject_id: UNBROKEN,
            reason_reference: UNBROKEN,
            requested_by: UNBROKEN,
            requested_at: "2019-03-04T09:00:00Z",
            finished_at: "2019-03-04T09:15:00Z",
            outcome: "incomplete",
            stores: [
              {
                store: "recording",
                disposition: "erase",
                reached: false,
                removed: 0,
                retired: 0,
                kept: 0,
                because: UNBROKEN,
              },
            ],
            holds: [],
          },
        ],
      },
      "/api/v1/govern/retention/exports": {
        exports: [
          {
            export_id: RUNG_ID,
            data_set: "audit_trail",
            requested_by: UNBROKEN,
            reason: "regulatory_request",
            reason_reference: UNBROKEN,
            produced_at: "2019-03-04T09:00:00Z",
            first_seq: 0,
            last_seq: 1,
            entries: 2,
            verified: true,
            document_digest: UNBROKEN,
          },
        ],
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
  // Notifications and email. The notice table scrolls; the relay's facts, the password line and
  // the sentences wrap. No control is pressed here: `tests/notifications-page.test.tsx` holds them.
  "/notifications": {
    address: "/notifications",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/notifications": NOTIFICATIONS },
  },
  // Storage. The bucket table scrolls; the address, the prefix and the sentences wrap.
  "/storage": {
    address: "/storage",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/storage": STORAGE },
  },
  // Secrets vault. The slot and lease tables scroll; the seal's sentence, the rotation and the
  // shipping sentences wrap outside them.
  "/vault": {
    address: "/vault",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/vault": VAULT },
  },
  // Requirement checks. The requirements table scrolls; the areas, the served sentence and the form
  // sit outside it.
  "/requirement-checks": {
    address: "/requirement-checks",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/requirements/checks": REQUIREMENT_CHECKS },
  },
  // Import and export. The catalogue and the exports tables scroll; the served sentences and the
  // export form sit outside them. The confirmation is held in `tests/data-transfer-page.test.tsx`.
  "/import-export": {
    address: "/import-export",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/data-transfer": DATA_TRANSFER },
  },
  // Compliance. A topic's named person and a connector's entities sit in tables that scroll; the
  // served sentences, a case's references and its findings sit outside them and must wrap. One
  // closed case and one open one, so every form a case draws is on the page. No control is
  // pressed here: the confirmations are held in `tests/compliance-page.test.tsx`.
  "/compliance": {
    address: "/compliance",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/compliance/topics": {
        topics: [
          {
            topic: "grievance",
            label: "Grievances",
            named: { principal_id: UNBROKEN, named_by: UNBROKEN, named_at: "2019-03-04T09:00:00Z" },
          },
          { topic: "salary", label: "Salary", named: null },
        ],
        tally: { period: "2019-03", total: null, by_topic: null, suppressed: true },
        referral: UNBROKEN,
        routing: UNBROKEN,
      },
      "/api/v1/govern/compliance/register": {
        connectors: [
          {
            connector: "xero",
            label: UNBROKEN,
            connected_by: UNBROKEN,
            connected_at: "2019-03-04T09:00:00Z",
            transport: "https",
            version: "1",
            entities: [{ entity: UNBROKEN, tier: "projected", fields: [UNBROKEN], classes: ["contact"] }],
            categories: ["contact"],
            write_capable: false,
            records_read: 12,
            documents_read: null,
            last_read_at: "2019-03-04T10:00:00Z",
            problem: UNBROKEN,
          },
        ],
        counts: UNBROKEN,
      },
      "/api/v1/govern/compliance/breaches": {
        cases: [
          {
            case_id: "22222222-2222-4222-8222-222222222222",
            became_aware_at: "2019-03-01T09:00:00Z",
            clock_starts_at: "2019-03-01T09:00:00Z",
            awareness_basis: "observed",
            awareness_source: "internal_detection",
            recorded_by: UNBROKEN,
            evidence_reference: UNBROKEN,
            assessed_at: "2019-03-02T09:00:00Z",
            significant_harm: false,
            affected_count: 3,
            outcome: "not_notifiable",
            commission_notified_at: null,
            individuals_notified_at: null,
            exception_ground: null,
            closed_at: "2019-03-03T09:00:00Z",
            closed_by: UNBROKEN,
            obligations: [],
            findings: [],
            closable: false,
          },
          {
            case_id: RUNG_ID,
            became_aware_at: "2019-03-04T09:00:00Z",
            clock_starts_at: "2019-03-04T08:00:00Z",
            awareness_basis: "estimated",
            awareness_source: "staff_report",
            recorded_by: UNBROKEN,
            evidence_reference: UNBROKEN,
            assessed_at: null,
            significant_harm: null,
            affected_count: null,
            outcome: null,
            commission_notified_at: null,
            individuals_notified_at: null,
            exception_ground: null,
            closed_at: null,
            closed_by: null,
            obligations: [
              {
                kind: "assess",
                basis: "guideline",
                due_before: "2019-04-03T08:00:00Z",
                satisfied: false,
                overdue: true,
                satisfied_late: false,
                out_of_order: false,
              },
            ],
            findings: [UNBROKEN],
            closable: false,
          },
        ],
        closing: UNBROKEN,
      },
    },
  },
  // Referred to me. The asker's reference sits in the table, which scrolls; the state sentence
  // beside it wraps. The confirmation is held in `tests/referrals-page.test.tsx`.
  "/referrals": {
    address: "/referrals",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/me/referrals": {
        referrals: [
          {
            referral_id: RUNG_ID,
            topic: "grievance",
            label: "Grievances",
            asked_by: UNBROKEN,
            asked_at: "2019-03-04T09:00:00Z",
            handled_at: null,
            handled_by: null,
          },
        ],
      },
    },
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
  [STAFF_LIST_RETURN_PATH]: {
    address: `${STAFF_LIST_RETURN_PATH}?code=X&state=Y`,
    signedIn: false,
    drawsValues: false,
    answers: {},
  },
};
