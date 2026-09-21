/**
 * The Models and health screen: the design's four figures, its chain table and its two cards,
 * each drawn from the route that owns it, the provider health card drawn from the plan the next
 * call makes, and the two provider controls, each sent only from a confirmation.
 *
 * The failures worth testing are the ones that look like SCREEN 11. A rung nothing has called
 * drawn as healthy looks like the design and says a provider nobody has asked anything is fine; a
 * fallback figure of zero drawn while the ledger cannot count fallbacks looks like the design and
 * says the chain never stepped down. Both are asserted against over the rendered page.
 *
 * **Five routes, and a refusal from one is drawn in its own card.** The tests hand each route its
 * own answer, including a refusal from the matrix and from the providers route while the rest
 * answer, because a page that waited on all five or failed on any one would hide four answers
 * behind the one that did not come back.
 *
 * **The page is mounted on its own**, for `tests/live-runs-page.test.tsx`' reason: the route table
 * is a shared file, and `.scratch/wire_live_runs_models.md` holds what goes into it.
 *
 * Task ids: M27.2.3, M27.8.8
 */

import { DOWNLOAD_REGISTER } from "../src/pages/providerRegisterQuery";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  COST,
  FALLBACKS_FIRED,
  FALLBACKS_NOTE,
  MORE_RUNGS,
  NO_BUDGET_OR_LATENCY_PER_TIER,
  NO_MODEL,
  NO_REQUESTS,
  NO_RUNG,
  NO_SPEND,
  NOT_MEASURED,
  OUT_OF_ROTATION,
  P95_ANSWER,
  PROVIDERS_CAPTION,
  RUNGS_CAPTION,
  SOMETHING_DID_NOT_WORK,
  SPEND_NOT_BUILT,
  UNREADABLE_ANSWER,
  WITHOUT_A_MODEL,
} from "../src/pages/Models";
import { MATRIX_PATH } from "../src/pages/matrixQuery";
import {
  ANSWERS_NOW,
  CHECK,
  checkConsequence,
  checkStatusSentence,
  credentialWords,
  exhaustedSentence,
  HEALTHY,
  healthWords,
  HOSTED_PROFILE_SENTENCE,
  HOURS_PARAMETER,
  KEEP_IT_AS_IT_IS,
  KEY_HELD,
  KEY_NOT_HELD,
  KEY_NOT_NEEDED,
  LOCAL_PROFILE_SENTENCE,
  MODELS_API_PATH,
  MODELS_PATH,
  NO_PROVIDER,
  NO_RUNG_ON_THE_LADDER,
  NOT_CALLED_YET,
  profileSentence,
  PROVIDERS_API_PATH,
  RESTING,
  RUNG_OUT_OF_ROTATION,
  SEND_THE_CHECK,
  SINCE_PARAMETER,
  spendShares,
  spendSinceApiPath,
  SWITCH_OFF,
  SWITCHED_OFF,
  SWITCHED_ON,
  switchConsequence,
  switchedSentence,
  switchQuestion,
  TIERS_CANNOT_ANSWER,
  UNHEALTHY_BECAUSE,
  VAULT_NOT_KNOWN,
  WINDOW_HOURS,
  withoutAModel,
  type RungStateRow,
} from "../src/pages/modelsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterNames, declaredParameterSchema, declaredQueryParameters } from "./support/openapi";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { everyWrite } from "./support/writes";

const CONSOLE_ORIGIN = "https://console.test";
const ROUTES = "src/brain/operate_routes.py";
const PROVIDER_ROUTES = "src/brain/provider_routes.py";
const MODELS = `/api/v1${MODELS_API_PATH}`;
const PROVIDERS = `/api/v1${PROVIDERS_API_PATH}`;
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

function rung(tier: string, position: number, model: string, extra: Record<string, unknown> = {}) {
  return {
    id: `${tier}-${String(position)}`,
    tier,
    position,
    role: position === 0 ? "primary" : "same_provider_failover",
    scope: {},
    deployment_id: `${model}-deployment`,
    provider: "anthropic",
    model,
    attempts: 1,
    timeout_seconds: 12,
    max_concurrency: 40,
    enabled: true,
    ...extra,
  };
}

function matrix(items: unknown[], truncated = false): Record<string, unknown> {
  return { items, next_cursor: null, total: null, truncated, editable: false, staleness: null };
}

const CHAIN = matrix([
  rung("main", 1, "claude-haiku-5"),
  rung("main", 0, "claude-sonnet-5"),
  rung("heavy", 0, "claude-opus-5", { enabled: false }),
  rung("heavy", 1, "local-8b", { provider: "local" }),
]);

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

/** One live rung in the shape `brain.provider_routes.RungStateView` serialises. */
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
    ...extra,
  } as RungStateRow;
}

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
      provider("local"),
    ],
    rungs: [
      liveRung("main", 0, "claude-sonnet-5"),
      liveRung("main", 1, "gpt-5", {
        provider: "openai",
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
        answers: true,
        state: "open",
        unhealthy_because: "timeout",
        live_seen: 1,
        live_failed: 1,
      }),
    ],
    exhausted_tiers: ["heavy"],
    editable: true,
    vault: null,
    vault_told: null,
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
  [RUNGS]: () => json(CHAIN),
  [LATENCY]: () => json(READING),
  [SPEND]: () => json(SPENT),
};

/** Mount the page on its own at its address, against five stand-in routes. */
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

const CHAIN_CAPTION = "Each tier's chain, in the order a request tries it";

describe("the four figures", () => {
  test("each figure is drawn from the route that owns it, and fallbacks fired is the ledger's number", async () => {
    // What breaks if this is deleted: a figure drawn from the wrong route, or Fallbacks fired still
    // drawn as "Not measured" on an install whose ledger sums every fallback, which hides the one
    // figure that says the chain is stepping down.
    const { container } = await modelsPage(EVERY_ANSWER);

    expect(figure(container, WITHOUT_A_MODEL)).toContain("30%");
    expect(figure(container, P95_ANSWER)).toContain("4100 ms");
    expect(figure(container, P95_ANSWER)).toContain("target 8000 ms");
    expect(figure(container, FALLBACKS_FIRED)).toBe(`12${FALLBACKS_NOTE}`);
    expect(figure(container, COST)).toContain("288.00");
    expect(figure(container, COST)).toContain("live");
  });

  test("while the API names the fallback count as unmeasured, the figure is its sentence and not a zero", async () => {
    // What breaks if this is deleted: a zero the ledger never counted drawn beside the design's
    // label, which says the chain never stepped down, on the day the ledger stops filling the field.
    const unmeasured = models({
      unmeasured: [{ measure: "fallback_count", because: "API-FALLBACK-BECAUSE" }],
      fallbacks_fired: 0,
    });
    const { container } = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json(unmeasured) });

    expect(figure(container, FALLBACKS_FIRED)).toBe(`${NOT_MEASURED}API-FALLBACK-BECAUSE`);
    expect(figure(container, FALLBACKS_FIRED)).not.toMatch(/\d/);
  });

  test("a window with no requests says so rather than drawing a share of nothing", async () => {
    // What breaks if this is deleted: "0%" answered without a model on a quiet install, which
    // says every request needed a model when none was made.
    const quiet = models({ lanes: [{ lane: "fast", requests: 0 }, { lane: "answer", requests: 0 }] });
    const { container } = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json(quiet) });

    expect(figure(container, WITHOUT_A_MODEL)).toContain(NO_REQUESTS);
    expect(figure(container, WITHOUT_A_MODEL)).not.toContain("%");
    expect(withoutAModel([{ lane: "answer", requests: 4 }])).toBe("0%");
  });

  test("a spend report nobody has built is a sentence in the figure and in its card", async () => {
    // What breaks if this is deleted: an unbuilt report drawn as a cost of 0.00, which is a
    // figure and a false one.
    const unbuilt = { ...SPENT, built: false, lines: [], total_minor: null, as_of: null, freshness: "unstated" };
    const { container } = await modelsPage({ ...EVERY_ANSWER, [SPEND]: () => json(unbuilt) });

    expect(figure(container, COST)).toContain(SPEND_NOT_BUILT);
    expect(card(container, "models-spend").textContent).toContain(SPEND_NOT_BUILT);
    expect(container.textContent).not.toContain("0.00");
  });
});

describe("the priority and fallback table", () => {
  test("a row per tier in the API's order, with rungs by position whatever order they arrived in", async () => {
    // What breaks if this is deleted: a fallback drawn as the primary because the page drew rungs
    // in the order the matrix returned them, which is the one fact this table exists to state.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, CHAIN_CAPTION);

    expect(rows.map((row) => row[0])).toEqual(["none", "small", "main", "heavy"]);
    expect(rows.map((row) => row[1])).toEqual(["NONE-HANDLES", "SMALL-HANDLES", "MAIN-HANDLES", "HEAVY-HANDLES"]);
    expect(rows[2]?.[2]).toContain("claude-sonnet-5");
    expect(rows[2]?.[3]).toContain("claude-haiku-5");
  });

  test("the fast lane's tier is no model, an empty tier says nothing is configured, and a disabled rung says so", async () => {
    // What breaks if this is deleted: a tier with no rungs drawn blank, which reads as not loaded,
    // or a rung out of rotation drawn exactly like one in it.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, CHAIN_CAPTION);

    expect(rows[0]?.[2]).toBe(NO_MODEL);
    expect(rows[1]?.[2]).toBe(NO_RUNG);
    expect(rows[3]?.[2]).toContain(OUT_OF_ROTATION);
    expect(rows[3]?.[3]).not.toContain(OUT_OF_ROTATION);
    expect(container.textContent).toContain(NO_BUDGET_OR_LATENCY_PER_TIER);
  });

  test("a measurement the API names as unmeasured is said in the API's words, in the card it belongs to", async () => {
    // What breaks if this is deleted: a sentence kept in this console going on saying no model is
    // called after one is, which is what the console's own copies did in the commit that started
    // calling one. The API's sentence leaves with the ledger's reason; a copy here does not.
    const unmeasured = models({
      unmeasured: [
        { measure: "model", because: "API-MODEL-BECAUSE" },
        { measure: "provider", because: "API-PROVIDER-BECAUSE" },
      ],
    });
    const named = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json(unmeasured) });
    const quiet = await modelsPage(EVERY_ANSWER);

    expect(card(named.container, "models-chain").textContent).toContain("API-MODEL-BECAUSE");
    expect(card(named.container, "models-providers").textContent).toContain("API-PROVIDER-BECAUSE");
    expect(quiet.container.textContent).not.toMatch(/No model is called|No provider has been called/);
  });

  test("a tier deeper than three rungs gets a later column, and a full page says there is more", async () => {
    // What breaks if this is deleted: a fourth rung silently dropped from the table, which is a
    // chain drawn shorter than the one the router follows.
    const deep = matrix(
      [0, 1, 2, 3, 4].map((position) => rung("main", position, `model-${String(position)}`)),
      true,
    );
    const shallow = await modelsPage(EVERY_ANSWER);
    const { container } = await modelsPage({ ...EVERY_ANSWER, [RUNGS]: () => json(deep) });

    const main = tableRows(container, CHAIN_CAPTION)[2] ?? [];

    expect(main[5]).toContain("model-3");
    expect(main[5]).toContain("model-4");
    expect(container.textContent).toContain(MORE_RUNGS);
    expect(shallow.container.textContent).not.toContain("Later fallbacks");
    expect(shallow.container.textContent).not.toContain(MORE_RUNGS);
  });

  test("a refused matrix is the API's sentence in the chain card and every other card still draws", async () => {
    // What breaks if this is deleted: a reader without the matrix's grant shown a blank page, or
    // shown nothing about providers and spend they may read, because one card's refusal was
    // treated as the page's.
    const { container } = await modelsPage({
      ...EVERY_ANSWER,
      [RUNGS]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });

    const chain = card(container, "models-chain").textContent ?? "";
    expect(chain).toContain(SOMETHING_DID_NOT_WORK);
    expect(chain).toContain("TRACE-SENTINEL");
    expect(tableRows(container, PROVIDERS_CAPTION).map((row) => row[0])).toEqual(["anthropic", "openai", "local"]);
    expect(figure(container, COST)).toContain("288.00");
  });
});

describe("provider health", () => {
  test("each provider is drawn with what it is for, its switch with who and when, and the key held here", async () => {
    // What breaks if this is deleted: a provider switched off drawn as on, a switch nobody can
    // attribute, or a provider needing no key drawn as missing one, which on an administrative
    // screen is a claim a person acts on.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, PROVIDERS_CAPTION);

    expect(rows.map((row) => row.slice(0, 2))).toEqual([
      ["anthropic", "ANTHROPIC-DESCRIPTION"],
      ["openai", "OPENAI-DESCRIPTION"],
      ["local", "LOCAL-DESCRIPTION"],
    ]);
    expect(rows[0]?.[2]).toBe(SWITCHED_ON);
    expect(rows[1]?.[2]).toContain(SWITCHED_OFF);
    expect(rows[1]?.[2]).toContain("Switched off by u_admin at");
    expect(rows.map((row) => row[3])).toEqual([KEY_HELD, KEY_NOT_HELD, KEY_NOT_NEEDED]);
    expect(card(container, "models-providers").textContent).toContain(HOSTED_PROFILE_SENTENCE);
  });

  test("the vault's column is drawn only when the API sent a credential, and says what the vault answered", async () => {
    // What breaks if this is deleted: a column of dashes shown to every reader, which tells one who
    // may not manage credentials that there is something they are not shown, or a slot the vault
    // could not be asked about drawn as not held.
    const plain = await modelsPage(EVERY_ANSWER);
    expect(plain.container.textContent).not.toContain("In the vault");

    const slot = { slot: "providers/anthropic", description: "D", held: null, set_at: null };
    const managing = providers({
      providers: [provider("anthropic", { credential: slot }), provider("local")],
      vault: "unreachable",
      vault_told: "VAULT-TOLD-SENTINEL",
    });
    const { container } = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json(managing) });

    const rows = tableRows(container, PROVIDERS_CAPTION);
    expect(rows.map((row) => row[4])).toEqual([VAULT_NOT_KNOWN, "-"]);
    expect(container.textContent).toContain("VAULT-TOLD-SENTINEL");
    expect(credentialWords({ ...slot, held: false })).not.toBe(credentialWords(slot));
  });

  test("a rung nothing has called is drawn as not called yet, never as healthy, and a called one is", async () => {
    // What breaks if this is deleted: a closed breaker with no attempt behind it drawn as healthy,
    // which is every rung on a fresh install drawn green on the strength of nobody having looked.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, RUNGS_CAPTION);
    const uncalled = rows.find((row) => row[2] === "gpt-5") ?? [];
    const called = rows.find((row) => row[2] === "claude-sonnet-5") ?? [];

    expect(uncalled[5]).toBe(NOT_CALLED_YET);
    expect(uncalled[5]).not.toContain(HEALTHY);
    expect(called[5]).toBe(HEALTHY);
    expect(healthWords(liveRung("main", 0, "m", { measured: false, state: "open", unhealthy_because: "timeout" }))).toBe(
      NOT_CALLED_YET,
    );
  });

  test("a rung left out says the API's sentence for why, one out of rotation says so, and one that answers says it answers", async () => {
    // What breaks if this is deleted: a switched-off provider's rung drawn like one that answers, so
    // the chain an administrator reads is longer than the chain the next call walks.
    const { container } = await modelsPage(EVERY_ANSWER);

    const answers = Object.fromEntries(tableRows(container, RUNGS_CAPTION).map((row) => [row[2], row[4]]));

    expect(answers).toEqual({
      "claude-sonnet-5": ANSWERS_NOW,
      "gpt-5": "TOLD-SWITCHED-OFF-SENTINEL",
      "claude-opus-5": RUNG_OUT_OF_ROTATION,
      "local-8b": ANSWERS_NOW,
    });
  });

  test("an open breaker names why, recent calls are the API's counts, and an exhausted tier is a notice", async () => {
    // What breaks if this is deleted: a resting rung drawn without its reason, recent calls drawn as
    // a rate nothing measured, or a tier that cannot answer at all left for somebody to spot in a row.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, RUNGS_CAPTION);
    const resting = rows.find((row) => row[2] === "local-8b") ?? [];
    const healthy = rows.find((row) => row[2] === "claude-sonnet-5") ?? [];

    expect(resting[5]).toBe(`${RESTING}: ${UNHEALTHY_BECAUSE["timeout"] ?? ""}`);
    expect(resting[6]).toBe("1 recent call, 1 failed");
    expect(healthy[6]).toBe("5 recent calls, 1 failed");
    const notice = card(container, "models-providers").querySelector(".notice");
    expect(notice?.textContent).toContain(TIERS_CANNOT_ANSWER);
    expect(notice?.textContent).toContain(exhaustedSentence("heavy"));

    const none = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json(providers({ exhausted_tiers: [] })) });
    expect(none.container.textContent).not.toContain(TIERS_CANNOT_ANSWER);
  });

  test("every reason a breaker opens has words, read against the router's own list", () => {
    // What breaks if this is deleted: a trigger added to the router reaching this screen as its raw
    // value, or a word kept here for a trigger the router no longer has.
    const triggers = Object.values(backendEnumMembers("src/brain/models/routing.py", "FallbackTrigger")).sort();

    expect(Object.keys(UNHEALTHY_BECAUSE).sort()).toEqual(triggers);
  });

  test("the profile is said in words, and anything but hosted is read as local", () => {
    // What breaks if this is deleted: an unexpected profile drawn as hosted, which tells an
    // administrator questions may leave the building on an install where they may not.
    expect(profileSentence("hosted")).toBe(HOSTED_PROFILE_SENTENCE);
    expect(profileSentence("local")).toBe(LOCAL_PROFILE_SENTENCE);
    expect(profileSentence("HOSTED ")).toBe(LOCAL_PROFILE_SENTENCE);
  });

  test("no provider and no rung are sentences, and a refused or unreadable providers answer is said in the card", async () => {
    // What breaks if this is deleted: an empty ladder drawn as two headings over nothing, or a
    // refusal from the providers route blanking the chain and spend cards beside it.
    const empty = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json(providers({ providers: [], rungs: [], exhausted_tiers: [] })),
    });
    expect(card(empty.container, "models-providers").textContent).toContain(NO_PROVIDER);
    expect(card(empty.container, "models-providers").textContent).toContain(NO_RUNG_ON_THE_LADDER);

    const refused = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json({ message: "I could not find that.", trace_id: "PROVIDERS-TRACE" }, 404),
    });
    expect(card(refused.container, "models-providers").textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(card(refused.container, "models-providers").textContent).toContain("PROVIDERS-TRACE");
    expect(tableRows(refused.container, CHAIN_CAPTION)).toHaveLength(4);

    const unreadable = await modelsPage({ ...EVERY_ANSWER, [PROVIDERS]: () => json({ providers: "no" }) });
    expect(card(unreadable.container, "models-providers").textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("the provider controls", () => {
  test("switching a provider off is sent only from its confirmation, as PUT on:false, and the card is the plan it answers with", async () => {
    // What breaks if this is deleted: one press sending every department's questions away from a
    // provider, a switch sent the wrong way, or a card still drawing the old chain after the API
    // answered with the new one.
    const after = providers({
      providers: [
        provider("anthropic", { switched_on: false, switched_by: "u_me", switched_at: "2019-03-05T09:00:00Z" }),
        provider("local"),
      ],
      rungs: [liveRung("main", 0, "claude-sonnet-5", { answers: false, told: "TOLD-AFTER-SENTINEL" })],
      exhausted_tiers: [],
    });
    const { container, sent } = await modelsPage({
      ...EVERY_ANSWER,
      [`PUT ${PROVIDERS}/anthropic`]: () => json(after),
    });
    const puts = () => sent.filter((one) => one.method === "PUT");

    fireEvent.click(button(container, `${SWITCH_OFF}: anthropic`));
    const confirmation = container.querySelector(".confirm");
    expect(confirmation?.textContent).toContain(switchQuestion("anthropic", false));
    expect(confirmation?.textContent).toContain(switchConsequence("anthropic", false));
    expect(switchConsequence("anthropic", false)).toContain("no question is sent to anthropic");
    expect(puts()).toEqual([]);

    fireEvent.click(confirmButton(container, KEEP_IT_AS_IT_IS));
    expect(container.querySelector(".confirm")).toBeNull();
    expect(puts()).toEqual([]);

    fireEvent.click(button(container, `${SWITCH_OFF}: anthropic`));
    fireEvent.click(confirmButton(container, SWITCH_OFF));

    await waitFor(() => {
      expect(container.textContent).toContain(switchedSentence("anthropic", false));
    });
    expect(puts()).toEqual([{ method: "PUT", path: `${PROVIDERS}/anthropic`, body: { on: false } }]);
    expect(tableRows(container, PROVIDERS_CAPTION)[0]?.[2]).toContain(SWITCHED_OFF);
    expect(tableRows(container, RUNGS_CAPTION)[0]?.[4]).toBe("TOLD-AFTER-SENTINEL");
    expect(sent.filter((one) => one.method === "GET" && one.path === PROVIDERS)).toHaveLength(1);
  });

  test("a check is sent only from its confirmation, as a POST, and draws the told sentence with what answered and what it cost", async () => {
    // What breaks if this is deleted: a press that spends tokens under somebody's name with nothing
    // asked first, or a check whose outcome is not drawn, so the press looks like it did nothing.
    const { container, sent } = await modelsPage({
      ...EVERY_ANSWER,
      [`POST ${PROVIDERS}/anthropic/check`]: () => json(check()),
    });
    const posts = () => sent.filter((one) => one.method === "POST");

    fireEvent.click(button(container, `${CHECK}: anthropic`));
    const consequence = container.querySelector(".confirm")?.textContent ?? "";
    expect(consequence).toContain(checkConsequence("anthropic"));
    expect(checkConsequence("anthropic")).toMatch(/one short fixed sentence.*few tokens.*recorded under your name/);
    expect(posts()).toEqual([]);

    fireEvent.click(confirmButton(container, SEND_THE_CHECK));

    await waitFor(() => {
      expect(container.textContent).toContain("CHECK-TOLD-SENTINEL");
    });
    expect(posts()).toEqual([{ method: "POST", path: `${PROVIDERS}/anthropic/check`, body: null }]);
    const outcome = container.querySelector('[aria-label="Check of anthropic"]')?.textContent ?? "";
    expect(outcome).toContain("claude-sonnet-5-deployment");
    expect(outcome).toContain("14 tokens in and 2 tokens out");
    expect(outcome).toContain("CHECK-TRACE-SENTINEL");
  });

  test("a check that did not answer draws its told sentence and the provider's status, and nothing about a model", async () => {
    // What breaks if this is deleted: a failed check drawn with a served-by line of nulls, which
    // reads as a check that answered.
    const { container } = await modelsPage({
      ...EVERY_ANSWER,
      [`POST ${PROVIDERS}/anthropic/check`]: () =>
        json(
          check({
            answered: false,
            outcome: "stopped",
            told: "STOPPED-TOLD-SENTINEL",
            served_by: null,
            model: null,
            tokens_in: null,
            tokens_out: null,
            status: 401,
          }),
        ),
    });

    fireEvent.click(button(container, `${CHECK}: anthropic`));
    fireEvent.click(confirmButton(container, SEND_THE_CHECK));

    await waitFor(() => {
      expect(container.textContent).toContain("STOPPED-TOLD-SENTINEL");
    });
    const outcome = container.querySelector('[aria-label="Check of anthropic"]')?.textContent ?? "";
    expect(outcome).toContain(checkStatusSentence(401));
    expect(outcome).not.toContain("Answered by");
  });

  test("both provider writes are reached only through a confirmation in the source, with the methods their routes declare", () => {
    // What breaks if this is deleted: a second button added beside the confirmation that calls the
    // write directly, which every behaviour test above would still pass.
    const writes = everyWrite().filter((one) => one.file === "src/pages/Models.tsx");

    expect(writes.map((one) => [one.method, one.confirmed])).toEqual([
      ["PUT", true],
      ["POST", true],
    ]);
  }, 60_000);

  test("the controls are not drawn for a reader the API says may not use them", async () => {
    // What breaks if this is deleted: a switch drawn for somebody the route refuses, which is a
    // control that fails every time it is pressed. Presentation only: the route refuses anyway.
    const { container } = await modelsPage({
      ...EVERY_ANSWER,
      [PROVIDERS]: () => json(providers({ editable: false })),
    });

    // The register's download is the one control every reader of this screen may use: it reads the
    // register, and the route answers it to whoever may read the screen.
    const controls = [...container.querySelectorAll("button, form, input")].filter(
      (one) => one.textContent !== DOWNLOAD_REGISTER,
    );
    expect(controls).toHaveLength(0);
    const edit = [...container.querySelectorAll("a")].filter((one) => one.textContent === "Edit routing");
    expect(edit.map((one) => one.getAttribute("href"))).toEqual([MATRIX_PATH]);
  });
});

describe("spend by department", () => {
  test("each department is a bar of its share of the API's total and its cost, and an empty report says so", async () => {
    // What breaks if this is deleted: a bar drawn against a total this page summed itself, or an
    // empty breakdown drawn as a card with a heading and nothing under it.
    const { container } = await modelsPage(EVERY_ANSWER);
    const meters = [...container.querySelectorAll("meter")];

    expect(meters.map((one) => Number(one.getAttribute("value")).toFixed(3))).toEqual(["0.646", "0.354"]);
    expect(card(container, "models-spend").textContent).toContain("186.00");

    const empty = await modelsPage({
      ...EVERY_ANSWER,
      [SPEND]: () => json({ ...SPENT, lines: [], total_minor: 0 }),
    });
    expect(card(empty.container, "models-spend").textContent).toContain(NO_SPEND);
  });

  test("a report whose every line cost nothing draws empty bars rather than bars of no number", () => {
    // What breaks if this is deleted: a share divided by a total of zero, which is NaN, reaching a
    // meter as its value on the one install where every department genuinely spent nothing.
    const shares = spendShares({ ...SPENT, lines: [{ key: "web", cost_minor: 0 }], total_minor: 0 });

    expect(shares).toEqual([{ key: "web", costMinor: 0, share: 0 }]);
  });
});

describe("the page's own answer", () => {
  test("a refused models answer is the API's sentence and nothing on the page asks the other four routes", async () => {
    // What breaks if this is deleted: a reader refused this screen still sends four requests on
    // its behalf and is shown the cards they return beneath a refusal.
    const { container, idp } = await modelsPage({
      ...EVERY_ANSWER,
      [MODELS]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });

    expect(container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(
      idp.urls.some((url) => [RUNGS, LATENCY, SPEND, PROVIDERS].includes(new URL(url, CONSOLE_ORIGIN).pathname)),
    ).toBe(false);
  });

  test("an answer this console cannot read says so", async () => {
    // What breaks if this is deleted: a body from another release drawn as an install with no
    // providers and no tiers, or one without the fallbacks figure drawn with a blank beside it.
    const { container } = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json({ tiers: "no" }) });
    const older = await modelsPage({
      ...EVERY_ANSWER,
      [MODELS]: () => json({ ...models(), fallbacks_fired: undefined }),
    });

    expect(container.textContent).toContain(UNREADABLE_ANSWER);
    expect(older.container.textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("what the page asks for", () => {
  test("each request sends only parameters its route declares, over one seven day window", async () => {
    // What breaks if this is deleted: a parameter a route ignores, which FastAPI drops without a
    // word, so a card answers over the route's default window under a heading saying seven days.
    const { idp } = await modelsPage(EVERY_ANSWER);

    for (const path of [MODELS, LATENCY, SPEND]) {
      const declared = new Set(declaredQueryParameters(path, "get"));
      const asked = idp.urls
        .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === path)
        .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
      expect(asked.length, path).toBeGreaterThan(0);
      expect(asked.filter((name) => !declared.has(name)), path).toEqual([]);
    }
    const hours = idp.urls
      .filter((url) => [MODELS, LATENCY].includes(new URL(url, CONSOLE_ORIGIN).pathname))
      .map((url) => new URL(url, CONSOLE_ORIGIN).searchParams.get(HOURS_PARAMETER));
    expect(new Set(hours)).toEqual(new Set([String(WINDOW_HOURS)]));
    for (const path of [MODELS, LATENCY]) {
      expect(Number(declaredParameterSchema(path, "get", HOURS_PARAMETER).maximum)).toBeGreaterThanOrEqual(WINDOW_HOURS);
    }
    expect(declaredQueryParameters(SPEND, "get")).toContain(SINCE_PARAMETER);
    // The providers route declares no parameter, so it is asked once and with none.
    expect(declaredParameterNames(PROVIDERS, "get", "query")).toEqual([]);
    expect(
      idp.urls
        .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === PROVIDERS)
        .map((url) => new URL(url, CONSOLE_ORIGIN).search),
    ).toEqual([""]);
  });

  test("the spend window starts on the UTC day seven days before now", () => {
    // What breaks if this is deleted: a cost over a window a day longer or shorter than the one
    // the heading names, because the first day was taken in the browser's own time zone.
    const path = spendSinceApiPath("/report/spend", "department", new Date("2019-03-06T01:30:00Z"));

    expect(path).toBe("/report/spend?dimension=department&since=2019-02-27");
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.operate_routes` or
    // `brain.provider_routes` that this page goes on reading, which renders as nothing on every
    // card in production.
    const body = models({ unmeasured: [{ measure: "model", because: "B" }] });
    expect(Object.keys(body).sort()).toEqual(backendModelFields(ROUTES, "ModelsView").sort());
    const first = (from: Record<string, unknown>, key: string) =>
      Object.keys((from[key] as Record<string, unknown>[])[0] ?? {}).sort();
    expect(first(body, "tiers")).toEqual(backendModelFields(ROUTES, "TierView").sort());
    expect(first(body, "lanes")).toEqual(backendModelFields(ROUTES, "LaneTrafficView").sort());
    expect(first(body, "providers")).toEqual(backendModelFields(ROUTES, "ProviderView").sort());
    expect(first(body, "unmeasured")).toEqual(backendModelFields(ROUTES, "UnmeasuredView").sort());

    const plan = providers();
    expect(Object.keys(plan).sort()).toEqual(backendModelFields(PROVIDER_ROUTES, "ProvidersView").sort());
    expect(first(plan, "providers")).toEqual(backendModelFields(PROVIDER_ROUTES, "ProviderStateView").sort());
    expect(first(plan, "rungs")).toEqual(backendModelFields(PROVIDER_ROUTES, "RungStateView").sort());
    expect(Object.keys(check()).sort()).toEqual(backendModelFields(PROVIDER_ROUTES, "CheckView").sort());
    expect(backendModelFields(PROVIDER_ROUTES, "ProviderSwitchAsked")).toEqual(["on"]);
  });
});
