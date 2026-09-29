/**
 * The fixtures more than one module's page cases answer with, and the shape of a case.
 *
 * **Only what two modules share lives here.** A fixture that one module's pages alone answer with
 * sits in that module's file under `pageCases/`, so rebuilding a module edits its own file and no
 * other. This is the remainder, and the module files import it, never `pageCases.ts`: that file
 * reads every module file eagerly, so a module file importing it back would read its constants
 * before they exist.
 *
 * The values are identifier-shaped tokens with nowhere to break, because that is what the phone
 * test needs, and the state test does not care what the values are.
 *
 * Task ids: none
 */

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

export const MATRIX = {
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

/** One person as the directory sends one, every value an unbreakable token. */
export const PERSON = {
  principal_id: "p_1",
  display_name: UNBROKEN,
  department: UNBROKEN,
  department_name: UNBROKEN,
  employment: "contractor",
  standing: "live",
  second_factor: false,
  last_signed_in_at: "2019-03-04T09:00:00Z",
  packs: [UNBROKEN],
};

/** One page of the directory: every person, grant or none. */
export const DIRECTORY = {
  items: [PERSON],
  next_cursor: null,
  truncated: false,
  editable: true,
  may_disable: true,
  may_add: true,
  adding: UNBROKEN,
  disabling: UNBROKEN,
  staleness: null,
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
export const AUDIT = {
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
 * The providers answer every page of the Models and routing module reads: one provider whose slug,
 * description, model, deployment and vault slot are tokens with nowhere to break. It is editable,
 * names a credential and carries a registry row, a last test and what it was sent, so every control,
 * the key form and the terms form are drawn. The slug is the provider page's address too.
 */
export const PROVIDERS_PLAN = {
  profile: "hosted",
  providers: [
    {
      listed: 0,
      provider: UNBROKEN,
      description: UNBROKEN,
      hosted: true,
      switched_on: false,
      switched_by: UNBROKEN,
      switched_at: "2019-03-04T09:00:00Z",
      key_held: true,
      credential: { slot: UNBROKEN, description: UNBROKEN, held: true, set_at: "2019-03-04T09:00:00Z" },
      registered: {
        label: UNBROKEN,
        kind: "openai_compatible",
        base_url: `https://${UNBROKEN}.example`,
        models: [UNBROKEN],
        processing_region: UNBROKEN,
        residency_class: "region_pinned",
        storage_location: UNBROKEN,
        retention_terms: UNBROKEN,
        training_terms: UNBROKEN,
        agreement_url: null,
        lane_overrides: [{ lane: "answer", timeout_seconds: 10, attempts: null }],
      },
      disclosed: [{ category: "question", told: UNBROKEN, attempts: 3 }],
      last_check: { answered: false, outcome: "timeout", model: UNBROKEN, at: "2019-03-04T09:00:00Z" },
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
  next_cursor: null,
};

/** The same answer with its list page: the list route answers every provider as `items` too. */
export const PROVIDERS_ANSWER = { ...PROVIDERS_PLAN, items: PROVIDERS_PLAN.providers };

export const DEPARTMENTS = {
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
      shapeable: true,
    },
  ],
  next_cursor: null,
  unplaced: [{ principal_id: `${UNBROKEN}0`, display_name: UNBROKEN, disabled: false, department: UNBROKEN }],
  truncated: true,
  may_organise: true,
  may_found: true,
  may_draw_scopes: true,
  staleness: null,
  teams: UNBROKEN,
  leads: UNBROKEN,
  counted: UNBROKEN,
  organising: UNBROKEN,
  shaping: UNBROKEN,
  retiring_department: UNBROKEN,
  retiring_team: UNBROKEN,
  retiring_scope: UNBROKEN,
};

/**
 * Connect Lark's guide with the staff list switched on, as `brain.lark_connect_routes.LarkView`
 * sends it, so the Connectors and Staff sources pages draw Lark's connected card. Every drawn value
 * is the unbroken token.
 */
export const LARK_GUIDE = {
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
  connected: true,
  app_id: UNBROKEN,
  steps: [
    {
      key: "choose",
      title: UNBROKEN,
      text: UNBROKEN,
      sketch: { place: UNBROKEN, heading: UNBROKEN, menu: [], menu_mark: "", tabs: [], tab_mark: "", lines: [], button: "" },
      link: "",
      link_label: "",
      asks: [],
    },
  ],
  scopes: [{ name: UNBROKEN, what: UNBROKEN, read_only: true }],
  scope_import: UNBROKEN,
  platforms: ["larksuite.com"],
  platform: "larksuite.com",
  base: "",
  developer_console: "https://open.larksuite.com/app",
  events_address: "",
  channel_note: UNBROKEN,
  events: null,
  knowledge_note: UNBROKEN,
  test_note: UNBROKEN,
  staff_sources_screen: "/staff_sources",
  vault_told: "",
  last_test: {
    at: "2999-03-02T02:00:00Z",
    accepted: true,
    uses: [{ name: "staff_list", label: UNBROKEN, verdict: "working" }],
  },
  switch_off_note: UNBROKEN,
  staff_off_note: UNBROKEN,
};

/** The staff list's runs, as the Lark card's last sync reads them. */
export const STAFF_RUNS = {
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
};
