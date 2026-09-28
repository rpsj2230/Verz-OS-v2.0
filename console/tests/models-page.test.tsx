/**
 * The Models and health screen as the owner drew it: where answers are made, the providers with a
 * status in words and their key, test and switch on the row, the failover matrix grouped by level
 * with a default pill and the API's role words, the month's cost, and everything else under a
 * closed Advanced.
 *
 * The failures worth testing are the ones that look like his screenshot. A step nothing has
 * called drawn as working looks like the design and says a provider nobody has asked anything is
 * fine; a fallback drawn under the wrong level, or a primary drawn second because the rows arrived
 * out of order, looks like the design and says the wrong model answers. Each is asserted against
 * over the rendered page, and every write is sent only from its confirmation.
 *
 * **Four routes, and a refusal from one is drawn in its own card.** The tests hand each route its
 * own answer, including refusals, because a page that waited on all four or failed on any one
 * would hide three answers behind the one that did not come back.
 *
 * **The page is mounted on its own**, for `tests/live-runs-page.test.tsx`' reason: the route table
 * is a shared file.
 *
 * Task ids: M27.2.3, M27.8.8, M5.7.1, M5.7.3, M5.2.2, M5.4.3, M5.4.8, M5.5.1
 */

import { DOWNLOAD_REGISTER, REGISTER_HEADING } from "../src/pages/providerRegisterQuery";
import {
  ADD_RESIDENCY,
  ALERTS_CAPTION,
  EDIT_NUMBERS,
  PRODUCT_DEFAULT,
  RESET_TIER,
  RESIDENCY_CAPTION,
  RETIRE_RESIDENCY,
  SAVE_NUMBERS,
  SET_HERE,
  TIERS_CAPTION,
  alertSentence,
  residencyConsequence,
  tierConsequence,
} from "../src/pages/routingSettingsQuery";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  COST_THIS_MONTH,
  EDIT,
  FALLBACKS_FIRED,
  FALLBACKS_NOTE,
  MATRIX_CAPTION,
  NO_REQUESTS,
  NO_SPEND_THIS_MONTH,
  NOT_MEASURED,
  P95_ANSWER,
  PINNED_FIRST,
  PROVIDER_DETAILS_CAPTION,
  PROVIDERS_CAPTION,
  SOMETHING_DID_NOT_WORK,
  SPEND_NOT_BUILT,
  STEPS_CAPTION,
  UNREADABLE_ANSWER,
  WITHOUT_A_MODEL,
} from "../src/pages/Models";
import { MATRIX_PATH } from "../src/pages/matrixQuery";
import {
  ADD_KEY,
  checkConsequence,
  checkStatusSentence,
  DO_NOT_TEST,
  exhaustedSentence,
  HEALTHY,
  healthWords,
  KEY_REFUSED,
  KEY_REFUSED_HEALTH,
  KEY_REFUSED_MARKER,
  HOURS_PARAMETER,
  KEEP_IT_AS_IT_IS,
  LEVEL_NAMES,
  LEVELS_CANNOT_ANSWER,
  matrixRows,
  MODELS_API_PATH,
  MODELS_PATH,
  monthStart,
  NO_STEP_FOR_THE_LEVEL,
  NOT_CALLED_YET,
  profileChosenSentence,
  profileConsequence,
  PROVIDER_NAMES,
  providerStatus,
  PROVIDERS_API_PATH,
  REPLACE_KEY,
  RESTING,
  ROLE_WORDS,
  SEND_THE_TEST,
  SERVER_ONLY,
  SINCE_PARAMETER,
  SKIPPED_MARKERS,
  spendShares,
  spendThisMonthApiPath,
  STEP_PAUSED,
  stepMarker,
  switchConsequence,
  switchedSentence,
  switchQuestion,
  TEST,
  TURN_OFF,
  UNHEALTHY_BECAUSE,
  VAULT_NOT_KNOWN,
  WINDOW_HOURS,
  withoutAModel,
  type ProviderStateRow,
  type RungStateRow,
} from "../src/pages/modelsQuery";
import {
  credentialPath,
  KEEP_THE_OLD_KEY,
  keySavedSentence,
  NOTHING_TYPED,
  SAVE_THE_KEY,
  saveKeyConsequence,
  saveKeyQuestion,
} from "../src/components/ProviderKeyForm";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterNames, declaredParameterSchema, declaredQueryParameters } from "./support/openapi";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { readRepoFile } from "./support/repo";
import { CURRENCY_NOT_SET, instantWords, moneyWords } from "../src/pages/spendQuery";
import { SETTINGS_PATH } from "../src/pages/settingsQuery";
import { everyWrite } from "./support/writes";

const CONSOLE_ORIGIN = "https://console.test";
const ROUTES = "src/brain/operate_routes.py";
const PROVIDER_ROUTES = "src/brain/provider_routes.py";
const MODELS = `/api/v1${MODELS_API_PATH}`;
const PROVIDERS = `/api/v1${PROVIDERS_API_PATH}`;
const PROFILE = "/api/v1/models/profile";
const RUNGS = "/api/v1/routing/rungs";
const LATENCY = "/api/v1/report/service-levels";
const SPEND = "/api/v1/report/spend";

/** One answer in the shape `brain.operate_routes.ModelsView` serialises. */
function models(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    start: "2019-02-27T09:00:00Z",
    end: "2019-03-06T09:00:00Z",
    tiers: [
      { tier: "none", handles: "NONE-HANDLES" },
      { tier: "small", handles: "SMALL-HANDLES" },
      { tier: "main", handles: "MAIN-HANDLES" },
      { tier: "heavy", handles: "HEAVY-HANDLES" },
    ],
    lanes: [
      { lane: "fast", requests: 3 },
      { lane: "answer", requests: 7 },
      { lane: "task", requests: 0 },
    ],
    providers: [
      { provider: "anthropic", description: "ANTHROPIC-DESCRIPTION" },
      { provider: "openai", description: "OPENAI-DESCRIPTION" },
    ],
    unmeasured: [],
    fallbacks_fired: 12,
    ...overrides,
  };
}

/** One provider in the shape `brain.provider_routes.ProviderStateView` serialises. */
function provider(name: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    provider: name,
    description: `${name.toUpperCase()}-DESCRIPTION`,
    hosted: name !== "local",
    switched_on: true,
    switched_by: null,
    switched_at: null,
    key_held: name === "local" ? null : true,
    credential: null,
    registered: null,
    disclosed: [],
    ...extra,
  };
}

/** One live step in the shape `brain.provider_routes.RungStateView` serialises. */
function liveRung(tier: string, position: number, model: string, extra: Record<string, unknown> = {}): RungStateRow {
  return {
    rung_id: `${tier}-${String(position)}`,
    tier,
    position,
    role: position === 0 ? "primary" : "same_provider_failover",
    deployment_id: `${model}-deployment`,
    provider: "anthropic",
    model,
    enabled: true,
    answers: true,
    skipped_because: null,
    told: null,
    state: "closed",
    measured: true,
    unhealthy_because: null,
    live_seen: 5,
    live_failed: 1,
    probes_seen: 3,
    probes_failed: 1,
    last_probe_at: "2019-03-06T08:59:00Z",
    last_live_at: "2019-03-06T08:00:00Z",
    key_refused: false,
    ...extra,
  } as RungStateRow;
}

/**
 * The steps, deliberately out of order: the Medium level arrives position 1, 0, 3, 2, so a page
 * drawing them in arrival order draws a fallback as the default.
 */
const STEPS: RungStateRow[] = [
  liveRung("main", 1, "claude-haiku-5"),
  liveRung("main", 0, "claude-sonnet-5"),
  liveRung("main", 3, "kimi-k2", {
    provider: "moonshot",
    role: "cross_provider_failover",
    answers: false,
    skipped_because: "no_key",
    told: "TOLD-NO-KEY-SENTINEL",
    measured: false,
    live_seen: 0,
    live_failed: 0,
  }),
  liveRung("main", 2, "gpt-5", {
    provider: "openai",
    role: "cross_provider_failover",
    answers: false,
    skipped_because: "switched_off",
    told: "TOLD-SWITCHED-OFF-SENTINEL",
    measured: false,
    live_seen: 0,
    live_failed: 0,
  }),
  liveRung("heavy", 0, "claude-opus-5", { enabled: false, answers: false }),
  liveRung("heavy", 1, "local-8b", {
    provider: "local",
    role: "cross_provider_failover",
    state: "open",
    unhealthy_because: "timeout",
    live_seen: 1,
    live_failed: 1,
  }),
];

/** One answer in the shape `brain.provider_routes.ProvidersView` serialises. */
function providers(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    profile: "hosted",
    providers: [
      provider("anthropic"),
      provider("openai", {
        switched_on: false,
        switched_by: "u_admin",
        switched_at: "2019-03-04T09:00:00Z",
        key_held: false,
      }),
      provider("moonshot", { key_held: false }),
      provider("deepseek"),
      provider("local"),
    ],
    rungs: STEPS,
    exhausted_tiers: ["heavy"],
    editable: true,
    vault: null,
    vault_told: null,
    tiers: [
      { tier: "small", context_window: 128000, escalation_headroom: 0.8, configured: false },
      { tier: "main", context_window: 50000, escalation_headroom: 0.5, configured: true },
      { tier: "heavy", context_window: 200000, escalation_headroom: 0.8, configured: false },
    ],
    residency: [
      {
        id: "44444444-4444-4444-8444-444444444444",
        scope: { clauses: [{ field: "department", op: "eq", value: "finance" }] },
        allowed_regions: ["eu-west-1"],
        on_prem_only: false,
        note: "NOTE-SENTINEL",
        created_by: "u_admin",
        created_at: "2019-03-04T09:00:00Z",
      },
    ],
    depth_alerts: [
      {
        raised_at: "2019-03-06T08:30:00Z",
        level: "warning",
        tier: "main",
        depth: 2,
        served_by: "gpt-5-deployment",
        reason: "REASON-SENTINEL",
        trace_id: "TRACE-SENTINEL",
      },
    ],
    profile_editable: false,
    ...overrides,
  };
}

/** One answer in the shape `brain.provider_routes.CheckView` serialises. */
function check(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    provider: "anthropic",
    answered: true,
    outcome: "answered",
    told: "CHECK-TOLD-SENTINEL",
    served_by: "claude-sonnet-5-deployment",
    model: "claude-sonnet-5",
    tokens_in: 14,
    tokens_out: 2,
    status: null,
    trace_id: "CHECK-TRACE-SENTINEL",
    default_model: false,
    ...overrides,
  };
}

const READING = {
  start: "2019-02-27T09:00:00Z",
  end: "2019-03-06T09:00:00Z",
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
};

const SPENT = {
  dimension: "department",
  built: true,
  lines: [
    { key: "maintenance", cost_minor: 18_600 },
    { key: "web", cost_minor: 10_200 },
  ],
  machine_included: false,
  total_minor: 28_800,
  as_of: "2019-03-06T08:00:00Z",
  freshness: "live",
  currency: "SGD",
  time_zone: "Asia/Singapore",
};

/** Answers by path for a GET, and by `METHOD path` for anything else, each handed its body. */
type Answers = Partial<Record<string, (body: unknown) => Response>>;

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const EVERY_ANSWER: Answers = {
  [MODELS]: () => json(models()),
  [PROVIDERS]: () => json(providers()),
  [LATENCY]: () => json(READING),
  [SPEND]: () => json(SPENT),
};

/** Mount the page on its own at its address, against four stand-in routes. */
async function modelsPage(
  answers: Answers,
): Promise<{ container: HTMLElement; idp: FakeIdp; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const body: unknown = typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
      const answer = answers[method === "GET" ? path : `${method} ${path}`];
      if (answer === undefined) {
        return null;
      }
      sent.push({ method, path, body });
      return answer(body);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Models } = await import("../src/pages/Models");
  const router = createMemoryRouter(
    [
      { path: MODELS_PATH, element: <Models /> },
      { path: MATRIX_PATH, element: <p>routing</p> },
    ],
    { initialEntries: [MODELS_PATH] },
  );
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return { container, idp, sent };
}

/** The value drawn beside one of the figures' labels. */
function figure(container: HTMLElement, label: string): string {
  const row = [...container.querySelectorAll(".fields__row")].find(
    (one) => one.querySelector("dt")?.textContent === label,
  );
  return row?.querySelector("dd")?.textContent ?? "";
}

function tableRows(container: HTMLElement, caption: string): string[][] {
  const table = [...container.querySelectorAll("table")].find(
    (one) => one.querySelector("caption")?.textContent === caption,
  );
  return [...(table?.querySelectorAll("tbody tr") ?? [])].map((row) =>
    [...row.querySelectorAll("td")].map((cell) => cell.textContent ?? ""),
  );
}

function card(container: HTMLElement, id: string): HTMLElement {
  const found = container.querySelector<HTMLElement>(`[aria-labelledby="${id}"]`);
  if (found === null) {
    throw new Error(`No card labelled by ${id}.`);
  }
  return found;
}

function advanced(container: HTMLElement): HTMLDetailsElement {
  const found = container.querySelector<HTMLDetailsElement>("details.advanced");
  if (found === null) {
    throw new Error("No Advanced section.");
  }
  return found;
}

/** A button by its accessible name, which is its label or its text. */
function button(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find(
    (one) => (one.getAttribute("aria-label") ?? one.textContent ?? "") === name,
  );
  if (found === undefined) {
    throw new Error(`No button named ${name}.`);
  }
  return found;
}

/** The confirmation's own button with this text. */
function confirmButton(container: HTMLElement, text: string): HTMLButtonElement {
  const found = [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === text);
  if (found === undefined) {
    throw new Error(`The confirmation has no button reading ${text}.`);
  }
  return found as HTMLButtonElement;
}

const ANTHROPIC = PROVIDER_NAMES["anthropic"] ?? "";

describe("where answers are made", () => {
  test("the profile is said in the owner's words, and only a reader the API says may change it is offered the change", async () => {
    // What breaks if this is deleted: the install's consent for text to leave the server drawn in
    // the setting's words or not at all, or a change offered to somebody the route refuses.
    const plain = await modelsPage(EVERY_ANSWER);
    const where = card(plain.container, "models-where").textContent ?? "";
    expect(where).toContain("Online providers");
    expect(plain.container.querySelector('[aria-labelledby="models-where"] button')).toBeNull();

    const local = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json(providers({ profile: "local", profile_editable: true })),
    });
    expect(card(local.container, "models-where").textContent).toContain("On this server only");
    expect(button(local.container, "Use online providers")).toBeTruthy();
  });

  test("choosing online providers is sent only from its confirmation, and every card is the plan it answers with", async () => {
    // What breaks if this is deleted: one press sending every department's questions off the
    // server with nothing asked, a write sent the wrong way, or the providers still drawn as
    // unused after the API answered with the plan that uses them.
    const serverOnly = providers({
      profile: "local",
      profile_editable: true,
      rungs: [liveRung("main", 0, "claude-sonnet-5", { answers: false, skipped_because: "local_profile" })],
    });
    const { container, sent } = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json(serverOnly),
      [`PUT ${PROFILE}`]: () => json(providers({ profile_editable: true })),
    });
    const puts = () => sent.filter((one) => one.method === "PUT");
    expect(tableRows(container, PROVIDERS_CAPTION)[0]?.[1]).toBe(SERVER_ONLY);
    expect(tableRows(container, MATRIX_CAPTION)[1]?.[4]).toContain("not sent online");

    fireEvent.click(button(container, "Use online providers"));
    expect(container.querySelector(".confirm")?.textContent).toContain(profileConsequence("hosted"));
    expect(profileConsequence("hosted")).toContain("the text of a question and the passages found for it");
    fireEvent.click(confirmButton(container, KEEP_IT_AS_IT_IS));
    expect(puts()).toEqual([]);

    fireEvent.click(button(container, "Use online providers"));
    fireEvent.click(confirmButton(container, "Use online providers"));
    await waitFor(() => {
      expect(container.textContent).toContain(profileChosenSentence("hosted"));
    });
    expect(puts()).toEqual([{ method: "PUT", path: PROFILE, body: { profile: "hosted" } }]);
    expect(card(container, "models-where").textContent).toContain("Online providers");
    expect(tableRows(container, PROVIDERS_CAPTION)[0]?.[1]).toBe("Key saved, working");
  });
});

describe("the providers", () => {
  test("every provider is a row by the name a person knows, with its status in words", async () => {
    // What breaks if this is deleted: a provider switched off, keyless or resting drawn as
    // working, or a slug where the owner expects "Anthropic (Claude)".
    const { container } = await modelsPage(EVERY_ANSWER);

    expect(tableRows(container, PROVIDERS_CAPTION).map((row) => row.slice(0, 2))).toEqual([
      [ANTHROPIC, "Key saved, working"],
      ["OpenAI", "Turned off"],
      ["Moonshot (Kimi)", "No key"],
      ["DeepSeek", "Key saved, not used yet"],
      ["Local model", "Resting after errors"],
    ]);
  });

  test("a provider none of whose answering steps has been called is not used yet, never working", () => {
    // What breaks if this is deleted: every provider on a fresh install drawn working on the
    // strength of nobody having called it, which is `AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE`.
    const row = provider("anthropic") as unknown as ProviderStateRow;

    expect(providerStatus(row, [liveRung("main", 0, "m", { measured: false })]).kind).toBe("unused");
    expect(providerStatus(row, [liveRung("main", 0, "m")]).kind).toBe("working");
    expect(providerStatus(row, [liveRung("main", 0, "m", { state: "half_open" })]).kind).toBe("resting");
    expect(providerStatus(row, [liveRung("main", 0, "m", { enabled: false, state: "open" })]).kind).toBe("unused");
    expect(providerStatus(row, [liveRung("main", 0, "m")], "local").kind).toBe("server_only");
  });

  test("all four online providers are rows with Add key before any key is held", async () => {
    // What breaks if this is deleted: M5.7.1's "switched on from the console with a key" with no
    // row to put the key on for a provider nobody has keyed yet, which is where every install starts.
    const keyless = providers({
      providers: [
        ...["anthropic", "openai", "moonshot", "deepseek"].map((name) =>
          provider(name, {
            key_held: false,
            credential: { slot: `providers/${name}`, description: "D", held: false, set_at: null },
          }),
        ),
        provider("local"),
      ],
      rungs: [],
      exhausted_tiers: [],
      vault: "ready",
      vault_told: "VAULT-READY",
    });
    const { container } = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json(keyless) });

    const rows = tableRows(container, PROVIDERS_CAPTION);
    expect(rows.map((row) => row[0])).toEqual([ANTHROPIC, "OpenAI", "Moonshot (Kimi)", "DeepSeek", "Local model"]);
    expect(rows.slice(0, 4).map((row) => row[1])).toEqual(Array(4).fill("No keyNo key in the vault"));
    for (const name of [ANTHROPIC, "OpenAI", "Moonshot (Kimi)", "DeepSeek"]) {
      expect(button(container, `${ADD_KEY}: ${name}`).textContent).toBe(ADD_KEY);
    }
    expect(() => button(container, `${ADD_KEY}: Local model`)).toThrow();
  });

  test("the key actions and the vault's line are drawn only for a reader the API sent the vault's column to", async () => {
    // What breaks if this is deleted: a key button drawn for somebody the credentials route
    // refuses, or the owner unable to tell which providers the vault holds a key for, which is the
    // question he was left asking on 2026-09-28.
    const plain = await modelsPage(EVERY_ANSWER);
    expect([...plain.container.querySelectorAll("button")].some((one) => one.textContent === REPLACE_KEY)).toBe(false);
    expect(plain.container.textContent).not.toContain("in the vault");

    const managing = providers({
      providers: [
        provider("anthropic", {
          credential: { slot: "providers/anthropic", description: "D", held: true, set_at: "2019-03-05T09:00:00Z" },
        }),
        provider("moonshot", {
          key_held: false,
          credential: { slot: "providers/moonshot", description: "D", held: null, set_at: null },
        }),
        provider("local"),
      ],
      vault: "unreachable",
      vault_told: "VAULT-TOLD-SENTINEL",
    });
    const { container } = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json(managing) });

    const rows = tableRows(container, PROVIDERS_CAPTION);
    expect(rows[0]?.[1]).toContain("Key in the vault since");
    expect(rows[1]?.[1]).toContain(VAULT_NOT_KNOWN);
    expect(button(container, `${REPLACE_KEY}: ${ANTHROPIC}`)).toBeTruthy();
    expect(button(container, `${ADD_KEY}: Moonshot (Kimi)`)).toBeTruthy();
    expect(card(container, "models-providers").textContent).toContain("VAULT-TOLD-SENTINEL");
  });

  test("a blank key sends nothing, and a typed one is sent once from its confirmation to the slot the API named and never drawn back", async () => {
    // What breaks if this is deleted: a press that stores an empty key, a key replaced with nothing
    // asked first, a write to a slot the page made up rather than the one the API named, or the key
    // left in the field or drawn anywhere on the page after it was saved.
    const KEY_SENTINEL = "sk-TEST-KEY-SENTINEL-0001";
    const slot = { slot: "providers/anthropic", description: "D", held: true, set_at: "2019-03-05T09:00:00Z" };
    const managing = providers({ providers: [provider("anthropic", { credential: slot }), provider("local")] });
    const { container, sent } = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json(managing),
      [`PUT /api/v1${credentialPath("providers/anthropic")}`]: () =>
        json({ slot: "providers/anthropic", held: true, set_at: "2019-03-05T09:00:00Z", in_use: "here", told: "TOLD-SENTINEL" }),
    });
    const puts = () => sent.filter((one) => one.method === "PUT");
    const keyInput = () => container.querySelector<HTMLInputElement>('[data-slot="secret-field"] input');

    expect(keyInput()).toBeNull();
    fireEvent.click(button(container, `${REPLACE_KEY}: ${ANTHROPIC}`));
    fireEvent.click(button(container, SAVE_THE_KEY));
    expect(container.textContent).toContain(NOTHING_TYPED);
    expect(container.querySelector(".confirm")).toBeNull();
    expect(puts()).toEqual([]);

    fireEvent.input(keyInput() as HTMLInputElement, { target: { value: KEY_SENTINEL } });
    fireEvent.click(button(container, SAVE_THE_KEY));
    expect(container.querySelector(".confirm")?.textContent).toContain(saveKeyQuestion(ANTHROPIC));
    expect(container.querySelector(".confirm")?.textContent).toContain(saveKeyConsequence(ANTHROPIC, true));
    fireEvent.click(confirmButton(container, KEEP_THE_OLD_KEY));
    expect(puts()).toEqual([]);

    fireEvent.click(button(container, SAVE_THE_KEY));
    fireEvent.click(confirmButton(container, SAVE_THE_KEY));
    await waitFor(() => {
      expect(container.textContent).toContain(keySavedSentence(ANTHROPIC, "TOLD-SENTINEL"));
    });
    expect(puts()).toEqual([
      { method: "PUT", path: `/api/v1${credentialPath("providers/anthropic")}`, body: { value: KEY_SENTINEL } },
    ]);
    expect(keyInput()).toBeNull();
    expect(container.innerHTML).not.toContain(KEY_SENTINEL);
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "GET" && one.path === PROVIDERS)).toHaveLength(2);
    });
  });

  test("turning a provider off is sent only from its confirmation, as PUT on:false, and the matrix is the plan it answers with", async () => {
    // What breaks if this is deleted: one press sending every department's questions away from a
    // provider, a switch sent the wrong way, or a matrix still drawing the old plan after the API
    // answered with the new one.
    const after = providers({
      providers: [
        provider("anthropic", { switched_on: false, switched_by: "u_me", switched_at: "2019-03-05T09:00:00Z" }),
        provider("local"),
      ],
      rungs: [liveRung("main", 0, "claude-sonnet-5", { answers: false, skipped_because: "switched_off" })],
      exhausted_tiers: [],
    });
    const { container, sent } = await modelsPage({ ...EVERY_ANSWER, [`PUT ${PROVIDERS}/anthropic`]: () => json(after) });
    const puts = () => sent.filter((one) => one.method === "PUT");

    fireEvent.click(button(container, `${TURN_OFF}: ${ANTHROPIC}`));
    const confirmation = container.querySelector(".confirm");
    expect(confirmation?.textContent).toContain(switchQuestion(ANTHROPIC, false));
    expect(confirmation?.textContent).toContain(switchConsequence(ANTHROPIC, false));
    expect(puts()).toEqual([]);

    fireEvent.click(confirmButton(container, KEEP_IT_AS_IT_IS));
    expect(container.querySelector(".confirm")).toBeNull();
    expect(puts()).toEqual([]);

    fireEvent.click(button(container, `${TURN_OFF}: ${ANTHROPIC}`));
    fireEvent.click(confirmButton(container, TURN_OFF));
    await waitFor(() => {
      expect(container.textContent).toContain(switchedSentence(ANTHROPIC, false));
    });
    expect(puts()).toEqual([{ method: "PUT", path: `${PROVIDERS}/anthropic`, body: { on: false } }]);
    expect(tableRows(container, PROVIDERS_CAPTION)[0]?.[1]).toBe("Turned off");
    expect(tableRows(container, MATRIX_CAPTION)[1]?.[4]).toContain("provider turned off");
    expect(sent.filter((one) => one.method === "GET" && one.path === PROVIDERS)).toHaveLength(1);
  });

  test("a test is sent only from its confirmation, as a POST, and draws what answered and what it cost", async () => {
    // What breaks if this is deleted: a press that spends tokens under somebody's name with nothing
    // asked first, or a test whose outcome is not drawn, so the press looks like it did nothing.
    const { container, sent } = await modelsPage({
      ...EVERY_ANSWER,
      [`POST ${PROVIDERS}/anthropic/check`]: () => json(check()),
    });
    const posts = () => sent.filter((one) => one.method === "POST");

    fireEvent.click(button(container, `${TEST}: ${ANTHROPIC}`));
    expect(container.querySelector(".confirm")?.textContent).toContain(checkConsequence(ANTHROPIC));
    expect(checkConsequence(ANTHROPIC)).toMatch(/one short fixed sentence.*few tokens.*recorded under your name/);
    fireEvent.click(confirmButton(container, DO_NOT_TEST));
    expect(posts()).toEqual([]);

    fireEvent.click(button(container, `${TEST}: ${ANTHROPIC}`));
    fireEvent.click(confirmButton(container, SEND_THE_TEST));
    await waitFor(() => {
      expect(container.textContent).toContain("CHECK-TOLD-SENTINEL");
    });
    expect(posts()).toEqual([{ method: "POST", path: `${PROVIDERS}/anthropic/check`, body: null }]);
    const outcome = container.querySelector(`[aria-label="Test of ${ANTHROPIC}"]`)?.textContent ?? "";
    // The model is named in the API's own sentence; the deployment id is never drawn.
    expect(outcome).not.toContain("claude-sonnet-5-deployment");
    expect(outcome).toContain("14 tokens in and 2 tokens out");
    expect(outcome).toContain("CHECK-TRACE-SENTINEL");
  });

  test("a test that did not answer draws its told sentence and the provider's status, and nothing about a model", async () => {
    // What breaks if this is deleted: a failed test drawn with a served-by line of nulls, which
    // reads as a test that answered.
    const failed = check({
      answered: false,
      outcome: "stopped",
      told: "STOPPED-TOLD-SENTINEL",
      served_by: null,
      model: null,
      tokens_in: null,
      tokens_out: null,
      status: 401,
    });
    const { container } = await modelsPage({ ...EVERY_ANSWER, [`POST ${PROVIDERS}/anthropic/check`]: () => json(failed) });

    fireEvent.click(button(container, `${TEST}: ${ANTHROPIC}`));
    fireEvent.click(confirmButton(container, SEND_THE_TEST));
    await waitFor(() => {
      expect(container.textContent).toContain("STOPPED-TOLD-SENTINEL");
    });
    const outcome = container.querySelector(`[aria-label="Test of ${ANTHROPIC}"]`)?.textContent ?? "";
    expect(outcome).toContain(checkStatusSentence(401));
    expect(outcome).not.toContain("tokens in");
  });

  test("every write on the screen is reached only through a confirmation in the source, with the methods its routes declare", () => {
    // What breaks if this is deleted: a second button added beside a confirmation that calls the
    // write directly, which every behaviour test above would still pass.
    const writes = everyWrite().filter((one) => ["src/pages/Models.tsx", "src/components/ProviderKeyForm.tsx"].includes(one.file));

    expect(writes.map((one) => [one.file, one.method, one.address, one.confirmed])).toEqual([
      ["src/pages/Models.tsx", "PUT", "providerSwitchApiPath(pending.provider)", true],
      ["src/pages/Models.tsx", "POST", "providerCheckApiPath(pending.provider)", true],
      ["src/pages/Models.tsx", "PUT", "PROFILE_API_PATH", true],
      ["src/components/ProviderKeyForm.tsx", "PUT", "credentialPath(slot)", true],
    ]);
  }, 60_000);

  test("no control is drawn for a reader the API says may not use one, and the matrix still links to where steps are edited", async () => {
    // What breaks if this is deleted: a switch, a key field or the profile drawn for somebody the
    // route refuses, which is a control that fails every time it is pressed.
    const { container } = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json(providers({ editable: false, profile_editable: false })),
    });

    // The register's download is the one control every reader of this screen may use: it reads the
    // register, and the route answers it to whoever may read the screen.
    const controls = [...container.querySelectorAll("button, form, input")].filter(
      (one) => one.textContent !== DOWNLOAD_REGISTER,
    );
    expect(controls).toHaveLength(0);
    const edit = [...card(container, "models-matrix").querySelectorAll("a")].filter((one) => one.textContent === EDIT);
    expect(edit.map((one) => one.getAttribute("href"))).toEqual([MATRIX_PATH]);
  });

  test("a refused providers answer is the API's sentence in each card that reads it, and the cost still draws", async () => {
    // What breaks if this is deleted: a reader without the models grant shown a blank page, or the
    // cost card they may read hidden behind another route's refusal.
    const refused = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json({ message: "I could not find that.", trace_id: "PROVIDERS-TRACE" }, 404),
    });
    for (const id of ["models-where", "models-providers", "models-matrix"]) {
      expect(card(refused.container, id).textContent).toContain(SOMETHING_DID_NOT_WORK);
      expect(card(refused.container, id).textContent).toContain("PROVIDERS-TRACE");
    }
    expect(card(refused.container, "models-cost").textContent).toContain("288.00");

    const unreadable = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json({ providers: "no" }) });
    expect(card(unreadable.container, "models-providers").textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("the failover matrix", () => {
  test("each level is named once by the owner's word, and its steps are numbered from 1 in position order whatever order they arrived in", async () => {
    // What breaks if this is deleted: a fallback drawn as the default because the page drew steps in
    // the order the API sent them, which is the one fact this table exists to state, or "main" where
    // the owner's screenshot says Medium.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, MATRIX_CAPTION);
    expect(rows.map((row) => row.slice(0, 4))).toEqual([
      ["Simple", "", NO_STEP_FOR_THE_LEVEL, ""],
      ["Medium", "1", ANTHROPIC, "claude-sonnet-5"],
      ["", "2", ANTHROPIC, "claude-haiku-5"],
      ["", "3", "OpenAI", "gpt-5"],
      ["", "4", "Moonshot (Kimi)", "kimi-k2"],
      ["Complex", "1", ANTHROPIC, "claude-opus-5"],
      ["", "2", "Local model", "local-8b"],
    ]);
  });

  test("the default is a pill, a later step says same provider or next provider in the API's role, and a step that will not answer says why quietly", async () => {
    // What breaks if this is deleted: the Role column worked out again here and disagreeing with the
    // routing screen, or a step with no key drawn exactly like one that answers.
    const { container } = await modelsPage(EVERY_ANSWER);

    const roles = tableRows(container, MATRIX_CAPTION).map((row) => row[4]);
    expect(roles).toEqual([
      "",
      "default",
      "next model, same provider",
      "next provider provider turned off",
      "next provider no key",
      "default paused on the routing screen",
      "next provider resting after errors",
    ]);
    const table = [...container.querySelectorAll("table")].find((one) => one.querySelector("caption")?.textContent === MATRIX_CAPTION);
    const defaults = [...(table?.querySelectorAll(".badge") ?? [])].filter((one) => one.textContent === "default");
    expect(defaults).toHaveLength(2);
    expect(defaults.every((one) => one.classList.contains("tone--caution"))).toBe(true);
  });

  test("the rows are built from the plan alone, and a level the API lists with no step is kept", () => {
    // What breaks if this is deleted: a level with nothing set up left out, which reads as a level
    // that cannot be asked, or a step naming a level the API did not list dropped from the table.
    const body = providers({ tiers: [{ tier: "main", context_window: 1, escalation_headroom: 0.5, configured: false }] });
    const rows = matrixRows(body as never);

    expect(rows.map((row) => [row.level, row.step])).toEqual([
      ["Medium", 1],
      [null, 2],
      [null, 3],
      [null, 4],
      ["Complex", 1],
      [null, 2],
    ]);
  });

  test("an exhausted level is a notice naming it by its level, the Edit link goes to the routing screen, and the pin is said beside the matrix", async () => {
    // What breaks if this is deleted: a level that cannot answer at all left for somebody to spot in
    // a row, or M5.7.3's pin, which is tried before every step here, nowhere on the screen of steps.
    const { container } = await modelsPage(EVERY_ANSWER);

    const matrix = card(container, "models-matrix");
    expect(matrix.querySelector(".notice")?.textContent).toContain(LEVELS_CANNOT_ANSWER);
    expect(matrix.querySelector(".notice")?.textContent).toContain(exhaustedSentence("heavy"));
    expect(exhaustedSentence("heavy")).toContain("Complex");
    expect(matrix.textContent).toContain(PINNED_FIRST);
    expect(matrix.querySelector("a")?.getAttribute("href")).toBe(MATRIX_PATH);

    const none = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json(providers({ exhausted_tiers: [] })) });
    expect(none.container.textContent).not.toContain(LEVELS_CANNOT_ANSWER);
  });

  test("every level is a ladder tier, every role and every reason a step is left out has words, and every built-in provider has a name, read against the backend", () => {
    // What breaks if this is deleted: a role, a skip reason or a tier added to the router reaching
    // this screen as its raw value, or a fifth built-in provider drawn by its slug.
    const tiers = Object.values(backendEnumMembers("src/brain/models/routing.py", "Tier")).filter((one) => one !== "none");
    const slots = [...readRepoFile("src/brain/ops/provider_keys.py").matchAll(/^ {8}slug="([a-z0-9_]+)",$/gm)].map(
      (one) => one[1],
    );

    expect(Object.keys(LEVEL_NAMES).sort()).toEqual(tiers.sort());
    expect(Object.keys(ROLE_WORDS).sort()).toEqual(Object.values(backendEnumMembers("src/brain/models/routing.py", "RungRole")).sort());
    expect(Object.keys(SKIPPED_MARKERS).sort()).toEqual(
      Object.values(backendEnumMembers("src/brain/models/assembly.py", "RungSkip")).sort(),
    );
    expect(Object.keys(UNHEALTHY_BECAUSE).sort()).toEqual(
      Object.values(backendEnumMembers("src/brain/models/routing.py", "FallbackTrigger")).sort(),
    );
    expect(slots.length).toBeGreaterThanOrEqual(4);
    expect(Object.keys(PROVIDER_NAMES).sort()).toEqual([...slots, "local"].sort());
  });
});

describe("cost this month", () => {
  test("the cost is the API's total for the month with each department's line", async () => {
    // What breaks if this is deleted: a cost the page summed itself, or a card that says nothing
    // about where the money went.
    const { container } = await modelsPage(EVERY_ANSWER);

    const cost = card(container, "models-cost");
    expect(cost.querySelector("h2")?.textContent).toBe(COST_THIS_MONTH);
    expect(cost.querySelector(".figure")?.textContent).toBe("SGD 288.00");
    expect(figure(cost, "maintenance")).toBe("SGD 186.00");
    expect(figure(cost, "web")).toBe("SGD 102.00");
    expect(spendShares({ ...SPENT, lines: [{ key: "web", cost_minor: 0 }], total_minor: 0 })).toEqual([
      { key: "web", costMinor: 0, share: 0 },
    ]);
  });

  test("the cost is in the install's currency and its instant in the install's zone, whatever the browser's", async () => {
    // What breaks if this is deleted: "288.00" read in whichever currency the reader assumes, or
    // "2019-03-06T08:00:00Z" read as the local time it is not, which is what the owner was shown.
    const { container } = await modelsPage(EVERY_ANSWER);
    expect(card(container, "models-cost").textContent).toContain("live, as of 6 Mar 2019, 16:00");
    expect(card(container, "models-cost").textContent).not.toContain("2019-03-06T08:00:00Z");

    const unset = await modelsPage({ ...EVERY_ANSWER, [SPEND]: () => json({ ...SPENT, currency: "XXX", time_zone: "UTC" }) });
    // Never the code meaning none: the amount alone, and where the currency is set, beside it.
    const unsetCard = card(unset.container, "models-cost");
    expect(unsetCard.querySelector(".figure")?.textContent).toBe("288.00");
    expect(unsetCard.textContent).not.toContain("XXX");
    expect(unsetCard.textContent).toContain(CURRENCY_NOT_SET);
    expect(unsetCard.querySelector(`a[href="${SETTINGS_PATH}"]`)).not.toBeNull();
    expect(card(container, "models-cost").textContent).not.toContain(CURRENCY_NOT_SET);
    expect(moneyWords(28_800, "XXX")).toBe("288.00");
    expect(card(unset.container, "models-cost").textContent).toContain("live, as of 6 Mar 2019, 08:00");
    expect(instantWords("2019-03-06T08:00:00Z", "Nowhere/Atlantis")).toBe("2019-03-06T08:00:00Z");
    expect(instantWords("not a time", "UTC")).toBe("not a time");
    expect(moneyWords(28_800, "SGD")).toBe("SGD 288.00");
  });

  test("a report nobody has built is a sentence and not a zero, and an empty month says so", async () => {
    // What breaks if this is deleted: an unbuilt report drawn as a cost of 0.00, which is a figure
    // and a false one, or an empty month drawn as a heading over nothing.
    const unbuilt = { ...SPENT, built: false, lines: [], total_minor: null, as_of: null, freshness: "unstated" };
    const never = await modelsPage({ ...EVERY_ANSWER, [SPEND]: () => json(unbuilt) });
    expect(card(never.container, "models-cost").textContent).toContain(SPEND_NOT_BUILT);
    expect(card(never.container, "models-cost").textContent).not.toContain("0.00");

    const empty = await modelsPage({ ...EVERY_ANSWER, [SPEND]: () => json({ ...SPENT, lines: [], total_minor: 0 }) });
    expect(card(empty.container, "models-cost").textContent).toContain(NO_SPEND_THIS_MONTH);
  });

  test("the month starts on its first UTC day, wherever the browser is", () => {
    // What breaks if this is deleted: a browser west of Greenwich on the last evening of a month
    // asking for the month before, because the first day was taken in its own time zone.
    expect(monthStart(new Date("2019-03-06T01:30:00Z"))).toBe("2019-03-01");
    expect(monthStart(new Date("2019-02-28T23:30:00-05:00"))).toBe("2019-03-01");
    expect(spendThisMonthApiPath("/report/spend", "department", new Date("2019-03-06T01:30:00Z"))).toBe(
      "/report/spend?dimension=department&since=2019-03-01",
    );
  });
});

describe("advanced", () => {
  test("Advanced is closed by default and still holds the figures, the provider details, each step's health, the register and the routing settings", async () => {
    // What breaks if this is deleted: the owner's screen opening on ten tables again, or a table an
    // administrator needs (the register's terms, a level's numbers) deleted rather than moved.
    const { container } = await modelsPage(EVERY_ANSWER);
    const section = advanced(container);

    expect(section.open).toBe(false);
    const text = section.textContent ?? "";
    for (const caption of [PROVIDER_DETAILS_CAPTION, STEPS_CAPTION, TIERS_CAPTION, RESIDENCY_CAPTION, ALERTS_CAPTION]) {
      expect(text).toContain(caption);
    }
    expect(text).toContain(REGISTER_HEADING);
    expect(text).toContain(WITHOUT_A_MODEL);
    for (const id of ["models-where", "models-providers", "models-matrix", "models-cost"]) {
      expect(section.querySelector(`[aria-labelledby="${id}"]`)).toBeNull();
    }
  });

  test("each figure is drawn from the route that owns it, and fallbacks fired is the ledger's number or the API's sentence", async () => {
    // What breaks if this is deleted: a figure drawn from the wrong route, or a zero the ledger
    // never counted drawn beside the fallbacks label, which says the chain never stepped down.
    const { container } = await modelsPage(EVERY_ANSWER);
    expect(figure(container, WITHOUT_A_MODEL)).toContain("30%");
    expect(figure(container, P95_ANSWER)).toContain("4100 ms");
    expect(figure(container, FALLBACKS_FIRED)).toBe(`12${FALLBACKS_NOTE}`);

    const unmeasured = models({ unmeasured: [{ measure: "fallback_count", because: "API-FALLBACK-BECAUSE" }], fallbacks_fired: 0 });
    const said = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json(unmeasured) });
    expect(figure(said.container, FALLBACKS_FIRED)).toBe(`${NOT_MEASURED}API-FALLBACK-BECAUSE`);

    const quiet = models({ lanes: [{ lane: "fast", requests: 0 }, { lane: "answer", requests: 0 }] });
    const empty = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json(quiet) });
    expect(figure(empty.container, WITHOUT_A_MODEL)).toContain(NO_REQUESTS);
    expect(withoutAModel([{ lane: "answer", requests: 4 }])).toBe("0%");
  });

  test("a step nothing has called is drawn as not called yet, never healthy, and a left-out step says the API's sentence", async () => {
    // What breaks if this is deleted: a closed breaker with no attempt behind it drawn healthy, or a
    // switched-off provider's step drawn like one that answers.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = Object.fromEntries(tableRows(container, STEPS_CAPTION).map((row) => [row[2], row]));
    expect(rows["gpt-5"]?.[5]).toBe(NOT_CALLED_YET);
    expect(rows["claude-sonnet-5"]?.[5]).toBe(HEALTHY);
    expect(rows["gpt-5"]?.[4]).toBe("TOLD-SWITCHED-OFF-SENTINEL");
    expect(rows["claude-opus-5"]?.[4]).toBe(STEP_PAUSED);
    expect(rows["local-8b"]?.[5]).toBe(`${RESTING}: ${UNHEALTHY_BECAUSE["timeout"] ?? ""}`);
    expect(rows["local-8b"]?.[6]).toBe("1 recent call, 1 failed");
    expect(rows["claude-sonnet-5"]?.[7]).toBe("3 background checks, 1 failed");
    // The step column counts from 1 within the level, whatever the stored position.
    expect(rows["claude-sonnet-5"]?.[1]).toBe("1");
    expect(rows["claude-haiku-5"]?.[1]).toBe("2");
    expect(healthWords(liveRung("main", 0, "m", { measured: false, state: "open" }))).toBe(NOT_CALLED_YET);
    expect(tableRows(container, PROVIDER_DETAILS_CAPTION)[1]?.[2]).toContain("Switched off by u_admin at");
  });

  test("each level's numbers say whether a row sets them, and each alert its depth", async () => {
    // What breaks if this is deleted: a product default drawn as a setting somebody made, or a
    // chain that went deep leaving nothing to read.
    const { container } = await modelsPage(EVERY_ANSWER);

    expect(tableRows(container, TIERS_CAPTION).map((row) => row.slice(0, 4))).toEqual([
      ["Simple", "128000 tokens", "80%", PRODUCT_DEFAULT],
      ["Medium", "50000 tokens", "50%", SET_HERE],
      ["Complex", "200000 tokens", "80%", PRODUCT_DEFAULT],
    ]);
    expect(tableRows(container, RESIDENCY_CAPTION)[0]?.slice(0, 3)).toEqual(["department eq finance", "eu-west-1", "NOTE-SENTINEL"]);
    // The API's reason is the operator's log line; the screen says what happened in plain words.
    const alert = tableRows(container, ALERTS_CAPTION)[0];
    expect(alert?.slice(1, 4)).toEqual(["Warning", "Medium", "2"]);
    expect(alert?.[4]).toBe(
      alertSentence({
        raised_at: "",
        level: "warning",
        tier: "main",
        depth: 2,
        served_by: "gpt-5-deployment",
        reason: "",
        trace_id: "",
      }),
    );
    expect(container.textContent).not.toContain("REASON-SENTINEL");
    expect(container.querySelector(`button[aria-label="${RESET_TIER}: Medium"]`)).not.toBeNull();
    expect(container.querySelector(`button[aria-label="${RESET_TIER}: Simple"]`)).toBeNull();
  });

  test("a level's numbers are sent only from their confirmation, as PUT, and the page is the plan it answers with", async () => {
    // What breaks if this is deleted: one press re-routing every department's questions, or a body
    // the route does not read.
    const after = providers({ tiers: [{ tier: "small", context_window: 64000, escalation_headroom: 0.6, configured: true }] });
    const { container, sent } = await modelsPage({ ...EVERY_ANSWER, ["PUT /api/v1/models/tiers/small"]: () => json(after) });
    const puts = () => sent.filter((one) => one.method === "PUT");

    fireEvent.click(button(container, `${EDIT_NUMBERS}: Simple`));
    const form = container.querySelector<HTMLFormElement>('form[aria-label="Numbers for the Simple level"]');
    fireEvent.change(form?.querySelector('input[name="context_window"]') as HTMLInputElement, { target: { value: "64000" } });
    fireEvent.change(form?.querySelector('input[name="escalation_headroom"]') as HTMLInputElement, { target: { value: "0.6" } });
    fireEvent.submit(form as HTMLFormElement);
    expect(container.querySelector(".confirm")?.textContent).toContain(
      tierConsequence("small", { context_window: 64000, escalation_headroom: 0.6 }),
    );
    expect(puts()).toEqual([]);

    fireEvent.click(confirmButton(container, SAVE_NUMBERS));
    await waitFor(() => {
      expect(puts()).toEqual([
        { method: "PUT", path: "/api/v1/models/tiers/small", body: { context_window: 64000, escalation_headroom: 0.6 } },
      ]);
    });
    await waitFor(() => {
      expect(tableRows(container, TIERS_CAPTION)).toHaveLength(1);
    });
  });

  test("a residency constraint is sent only from its confirmation with its scope, and one is retired the same way", async () => {
    // What breaks if this is deleted: a constraint attached to the wrong scope, sent unasked, or a
    // retirement that widens where questions go with nothing confirmed.
    const retire = "/api/v1/models/residency/44444444-4444-4444-8444-444444444444/retire";
    const { container, sent } = await modelsPage({
      ...EVERY_ANSWER,
      ["POST /api/v1/models/residency"]: () => json(providers()),
      [`POST ${retire}`]: () => json(providers({ residency: [] })),
    });
    const posts = () => sent.filter((one) => one.method === "POST");

    const form = container.querySelector<HTMLFormElement>('form[aria-label="Add a rule on where questions may be processed"]');
    fireEvent.change(form?.querySelector('input[name="department"]') as HTMLInputElement, { target: { value: "legal" } });
    fireEvent.change(form?.querySelector('input[name="allowed_regions"]') as HTMLInputElement, {
      target: { value: "eu-west-1, eu-central-1" },
    });
    fireEvent.submit(form as HTMLFormElement);
    const asked = {
      scope: { clauses: [{ field: "department", op: "eq", value: "legal" }] },
      allowed_regions: ["eu-west-1", "eu-central-1"],
      on_prem_only: false,
      note: "",
    };
    expect(container.querySelector(".confirm")?.textContent).toContain(residencyConsequence(asked));
    expect(posts()).toEqual([]);
    fireEvent.click(confirmButton(container, ADD_RESIDENCY));
    await waitFor(() => {
      expect(posts()).toEqual([{ method: "POST", path: "/api/v1/models/residency", body: asked }]);
    });

    fireEvent.click(button(container, `${RETIRE_RESIDENCY}: department eq finance`));
    fireEvent.click(confirmButton(container, RETIRE_RESIDENCY));
    await waitFor(() => {
      expect(posts()).toHaveLength(2);
    });
    expect(posts()[1]?.path).toBe(retire);
  });

  test("the settings' writes are reached only through a confirmation in the source", () => {
    // What breaks if this is deleted: a later edit wiring one of the four writes to a plain button.
    const writes = everyWrite().filter((one) => one.file === "src/components/RoutingSettings.tsx");
    expect(writes.map((one) => [one.method, one.address, one.confirmed])).toEqual([
      ["PUT", "tierApiPath(asked.tier)", true],
      ["POST", "tierResetApiPath(asked.tier)", true],
      ["POST", "RESIDENCY_API_PATH", true],
      ["POST", "residencyRetireApiPath(asked.row.id)", true],
    ]);
  });
});

describe("plain words and a refused key", () => {
  test("a step whose latest call the provider refused as a key marks the provider and the step, never working or healthy", async () => {
    // What breaks if this is deleted: a provider that refuses its key drawn as "Key saved, working",
    // because a refused key does not open the breaker, which is what the owner's install showed.
    const refused = STEPS.map((one) => (one.model === "claude-sonnet-5" ? { ...one, key_refused: true } : one));
    const { container } = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json(providers({ rungs: refused })) });

    const status = tableRows(container, PROVIDERS_CAPTION).find((row) => row[0] === ANTHROPIC)?.[1] ?? "";
    expect(status).toContain(KEY_REFUSED);
    expect(status).not.toContain("working");
    const rows = Object.fromEntries(tableRows(container, STEPS_CAPTION).map((row) => [row[2], row]));
    expect(rows["claude-sonnet-5"]?.[5]).toBe(KEY_REFUSED_HEALTH);
    expect(stepMarker({ ...(STEPS[1] as RungStateRow), key_refused: true })).toEqual(KEY_REFUSED_MARKER);
    expect(stepMarker(STEPS[1] as RungStateRow)).toBeNull();
    const row = provider("anthropic") as unknown as ProviderStateRow;
    expect(providerStatus(row, [liveRung("main", 0, "m", { key_refused: true })]).kind).toBe("key_refused");
    expect(providerStatus(row, [liveRung("main", 0, "m")]).kind).toBe("working");
  });

  test("no rung, ladder, tier, lane or slot is drawn anywhere on the screen, Advanced included", async () => {
    // What breaks if this is deleted: the owner's plain screen (2026-09-28: Simple, Medium, Complex,
    // step, provider, model) grows internal words again in the next sentence somebody writes. The
    // whole rendered page is read, Advanced and every closed section included, with a test's
    // outcome and a held level drawn.
    const { container } = await modelsPage({
      ...EVERY_ANSWER,
      [`POST ${PROVIDERS}/anthropic/check`]: () => json(check()),
    });
    fireEvent.click(button(container, `${TEST}: ${ANTHROPIC}`));
    fireEvent.click(confirmButton(container, SEND_THE_TEST));
    await waitFor(() => {
      expect(container.textContent).toContain("CHECK-TOLD-SENTINEL");
    });

    const words = container.textContent ?? "";
    expect(words).not.toMatch(/\b(rungs?|ladders?|tiers?|lanes?|slots?)\b/i);
    expect(words).not.toMatch(/\b(small|heavy)\b/);
  });
});

describe("the page's own answer", () => {
  test("a refused models answer is the API's sentence and nothing on the page asks the other three routes", async () => {
    // What breaks if this is deleted: a reader refused this screen still sends requests on its
    // behalf and is shown the cards they return beneath a refusal.
    const { container, idp } = await modelsPage({
      ...EVERY_ANSWER,
      [MODELS]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });

    expect(container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(idp.urls.some((url) => [RUNGS, LATENCY, SPEND, PROVIDERS].includes(new URL(url, CONSOLE_ORIGIN).pathname))).toBe(false);
  });

  test("an answer this console cannot read says so", async () => {
    // What breaks if this is deleted: a body from another release drawn as an install with no
    // providers and no levels.
    const { container } = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json({ tiers: "no" }) });

    expect(container.textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("what the page asks for", () => {
  test("each request sends only parameters its route declares, and the routing matrix is not asked for a second copy of the steps", async () => {
    // What breaks if this is deleted: a parameter a route ignores, which FastAPI drops without a
    // word, so a card answers over the route's default window under a heading saying otherwise; or
    // the old matrix request coming back beside the providers answer that already carries the steps.
    const { idp } = await modelsPage(EVERY_ANSWER);
    const asked = (path: string) => idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === path);

    for (const path of [MODELS, LATENCY, SPEND]) {
      const declared = new Set(declaredQueryParameters(path, "get"));
      const names = asked(path).flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
      expect(names.length, path).toBeGreaterThan(0);
      expect(names.filter((name) => !declared.has(name)), path).toEqual([]);
    }
    for (const path of [MODELS, LATENCY]) {
      expect(new Set(asked(path).map((url) => new URL(url, CONSOLE_ORIGIN).searchParams.get(HOURS_PARAMETER)))).toEqual(
        new Set([String(WINDOW_HOURS)]),
      );
      expect(Number(declaredParameterSchema(path, "get", HOURS_PARAMETER).maximum)).toBeGreaterThanOrEqual(WINDOW_HOURS);
    }
    expect(asked(SPEND).map((url) => new URL(url, CONSOLE_ORIGIN).searchParams.get(SINCE_PARAMETER))).toEqual([
      monthStart(new Date()),
    ]);
    expect(declaredParameterNames(PROVIDERS, "get", "query")).toEqual([]);
    expect(asked(PROVIDERS).map((url) => new URL(url, CONSOLE_ORIGIN).search)).toEqual([""]);
    expect(asked(RUNGS)).toEqual([]);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.operate_routes` or
    // `brain.provider_routes` that this page goes on reading, which renders as nothing on every
    // card in production.
    const body = models({ unmeasured: [{ measure: "model", because: "B" }] });
    expect(Object.keys(body).sort()).toEqual(backendModelFields(ROUTES, "ModelsView").sort());
    const first = (from: Record<string, unknown>, key: string) =>
      Object.keys((from[key] as Record<string, unknown>[])[0] ?? {}).sort();
    expect(first(body, "lanes")).toEqual(backendModelFields(ROUTES, "LaneTrafficView").sort());
    expect(first(body, "unmeasured")).toEqual(backendModelFields(ROUTES, "UnmeasuredView").sort());

    const plan = providers();
    expect(Object.keys(plan).sort()).toEqual(backendModelFields(PROVIDER_ROUTES, "ProvidersView").sort());
    expect(first(plan, "providers")).toEqual(backendModelFields(PROVIDER_ROUTES, "ProviderStateView").sort());
    expect(first(plan, "rungs")).toEqual(backendModelFields(PROVIDER_ROUTES, "RungStateView").sort());
    expect(first(plan, "tiers")).toEqual(backendModelFields(PROVIDER_ROUTES, "RoutingTierView").sort());
    expect(Object.keys(check()).sort()).toEqual(backendModelFields(PROVIDER_ROUTES, "CheckView").sort());
    expect(Object.keys(SPENT).sort()).toEqual(backendModelFields("src/brain/report_routes.py", "SpendReportView").sort());
    expect(backendModelFields(PROVIDER_ROUTES, "ProviderSwitchAsked")).toEqual(["on"]);
    expect(backendModelFields(PROVIDER_ROUTES, "ProfileAsked")).toEqual(["profile"]);
  });
});
