/**
 * The Models and health screen: the design's four figures, its chain table and its two cards,
 * each drawn from the route that owns it, and what is said where the design draws something this
 * install cannot measure.
 *
 * The failures worth testing are the ones that look like SCREEN 11. A provider drawn with a full
 * green bar looks like the design and says a provider nobody has called is healthy; a fallback
 * figure of zero looks like the design and says the chain never stepped down when no chain runs.
 * Both are asserted against over the rendered page.
 *
 * **Four routes, and a refusal from one is drawn in its own card.** The tests hand each route its
 * own answer, including a refusal from the matrix while the rest answer, because a page that
 * waited on all four or failed on any one would hide three answers behind the one that did not
 * come back.
 *
 * **The page is mounted on its own**, for `tests/live-runs-page.test.tsx`' reason: the route table
 * is a shared file, and `.scratch/wire_live_runs_models.md` holds what goes into it.
 *
 * Task ids: M27.2.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  COST,
  FALLBACKS_FIRED,
  MORE_RUNGS,
  NO_BUDGET_OR_LATENCY_PER_TIER,
  NO_MODEL,
  NO_REQUESTS,
  NO_RUNG,
  NO_SPEND,
  NOT_MEASURED,
  OUT_OF_ROTATION,
  P95_ANSWER,
  SOMETHING_DID_NOT_WORK,
  SPEND_NOT_BUILT,
  UNREADABLE_ANSWER,
  WITHOUT_A_MODEL,
} from "../src/pages/Models";
import { MATRIX_PATH } from "../src/pages/matrixQuery";
import {
  HEALTH_NOT_RECORDED,
  HOURS_PARAMETER,
  KEY_STATUS_ARRIVES_WITH_THE_VAULT,
  MEASURE_SENTENCES,
  measureSentence,
  MODELS_API_PATH,
  MODELS_PATH,
  NO_KEY_SLOT,
  providerRows,
  SINCE_PARAMETER,
  spendShares,
  spendSinceApiPath,
  WINDOW_HOURS,
  withoutAModel,
} from "../src/pages/modelsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterSchema, declaredQueryParameters } from "./support/openapi";
import { backendModelFields } from "./support/python";

const CONSOLE_ORIGIN = "https://console.test";
const ROUTES = "src/brain/operate_routes.py";
const MODELS = `/api/v1${MODELS_API_PATH}`;
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
    unmeasured: [
      { measure: "model", because: "API-MODEL-BECAUSE" },
      { measure: "provider", because: "API-PROVIDER-BECAUSE" },
      { measure: "fallback_count", because: "API-FALLBACK-BECAUSE" },
    ],
    breaker_state_is_not_recorded: true,
    key_status_is_not_served: true,
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

type Answers = Partial<Record<string, () => Response>>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const EVERY_ANSWER: Answers = {
  [MODELS]: () => json(models()),
  [RUNGS]: () => json(CHAIN),
  [LATENCY]: () => json(READING),
  [SPEND]: () => json(SPENT),
};

/** Mount the page on its own at its address, against four stand-in routes. */
async function modelsPage(answers: Answers): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return answers[new URL(url, CONSOLE_ORIGIN).pathname]?.() ?? null;
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
  return { container, idp };
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

const CHAIN_CAPTION = "Each tier's chain, in the order a request tries it";
const PROVIDER_CAPTION = "Every provider this system can hold a key for, and where the chain names it";

describe("the four figures", () => {
  test("each figure is drawn from the route that owns it, and fallbacks are a sentence and not a zero", async () => {
    // What breaks if this is deleted: a figure drawn from the wrong route, or Fallbacks fired
    // drawn as 0, which says the chain never stepped down on an install where no chain runs.
    const { container } = await modelsPage(EVERY_ANSWER);

    expect(figure(container, WITHOUT_A_MODEL)).toContain("30%");
    expect(figure(container, P95_ANSWER)).toContain("4100 ms");
    expect(figure(container, P95_ANSWER)).toContain("target 8000 ms");
    expect(figure(container, FALLBACKS_FIRED)).toContain(NOT_MEASURED);
    expect(figure(container, FALLBACKS_FIRED)).toContain(MEASURE_SENTENCES.fallback_count);
    expect(figure(container, FALLBACKS_FIRED)).not.toMatch(/\d/);
    expect(figure(container, COST)).toContain("288.00");
    expect(figure(container, COST)).toContain("live");
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
    expect(container.querySelector('[aria-labelledby="models-spend"]')?.textContent).toContain(SPEND_NOT_BUILT);
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
    expect(container.textContent).toContain(MEASURE_SENTENCES.model);
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

    const chain = container.querySelector('[aria-labelledby="models-chain"]')?.textContent ?? "";
    expect(chain).toContain(SOMETHING_DID_NOT_WORK);
    expect(chain).toContain("TRACE-SENTINEL");
    expect(tableRows(container, PROVIDER_CAPTION).map((row) => row[0])).toEqual(["anthropic", "openai"]);
    expect(figure(container, COST)).toContain("288.00");
  });
});

describe("provider health", () => {
  test("every slot is a row with where the chain names it, health not recorded, and the key sentence", async () => {
    // What breaks if this is deleted: a provider drawn with a health figure nothing measured, or
    // the key column guessed, which on an administrative screen is a claim a person acts on.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, PROVIDER_CAPTION);

    expect(rows[0]).toEqual(["anthropic", "ANTHROPIC-DESCRIPTION", "heavy 0, main 0, main 1", HEALTH_NOT_RECORDED]);
    expect(rows[1]).toEqual(["openai", "OPENAI-DESCRIPTION", "-", HEALTH_NOT_RECORDED]);
    expect(container.textContent).toContain(KEY_STATUS_ARRIVES_WITH_THE_VAULT);
    expect(container.textContent).toContain(MEASURE_SENTENCES.provider);
    expect(container.querySelectorAll("meter")).toHaveLength(2);
  });

  test("a provider the chain names with no key slot is a row saying it cannot answer", async () => {
    // What breaks if this is deleted: a rung pointed at a provider this system cannot hold a key
    // for looks like any other row, and the chain fails at exactly the moment it is reached.
    const { container } = await modelsPage(EVERY_ANSWER);

    const rows = tableRows(container, PROVIDER_CAPTION);

    expect(rows[2]).toEqual(["local", NO_KEY_SLOT, "heavy 1", HEALTH_NOT_RECORDED]);
    expect(providerRows([], []).length).toBe(0);
  });

  test("an unmeasured measurement this console has no sentence for is shown in the API's words", () => {
    // What breaks if this is deleted: a new measurement the ledger cannot fill arrives with no
    // sentence at all, because the console's table did not know its name.
    expect(measureSentence("tokens_in", "API-TOKENS-BECAUSE")).toBe("API-TOKENS-BECAUSE");
    expect(measureSentence("provider", "API-PROVIDER-BECAUSE")).toBe(MEASURE_SENTENCES.provider);
  });
});

describe("spend by department", () => {
  test("each department is a bar of its share of the API's total and its cost, and an empty report says so", async () => {
    // What breaks if this is deleted: a bar drawn against a total this page summed itself, or an
    // empty breakdown drawn as a card with a heading and nothing under it.
    const { container } = await modelsPage(EVERY_ANSWER);
    const meters = [...container.querySelectorAll("meter")];

    expect(meters.map((one) => Number(one.getAttribute("value")).toFixed(3))).toEqual(["0.646", "0.354"]);
    expect(container.querySelector('[aria-labelledby="models-spend"]')?.textContent).toContain("186.00");

    const empty = await modelsPage({
      ...EVERY_ANSWER,
      [SPEND]: () => json({ ...SPENT, lines: [], total_minor: 0 }),
    });
    expect(empty.container.querySelector('[aria-labelledby="models-spend"]')?.textContent).toContain(NO_SPEND);
  });

  test("a report whose every line cost nothing draws empty bars rather than bars of no number", () => {
    // What breaks if this is deleted: a share divided by a total of zero, which is NaN, reaching a
    // meter as its value on the one install where every department genuinely spent nothing.
    const shares = spendShares({ ...SPENT, lines: [{ key: "web", cost_minor: 0 }], total_minor: 0 });

    expect(shares).toEqual([{ key: "web", costMinor: 0, share: 0 }]);
  });
});

describe("the page's own answer", () => {
  test("a refused models answer is the API's sentence and nothing on the page asks the other three routes", async () => {
    // What breaks if this is deleted: a reader refused this screen still sends three requests on
    // its behalf and is shown the cards they return beneath a refusal.
    const { container, idp } = await modelsPage({
      ...EVERY_ANSWER,
      [MODELS]: () => json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    });

    expect(container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(idp.urls.some((url) => url.includes(RUNGS) || url.includes(LATENCY) || url.includes(SPEND))).toBe(false);
  });

  test("an answer this console cannot read says so", async () => {
    // What breaks if this is deleted: a body from another release drawn as an install with no
    // providers and no tiers.
    const { container } = await modelsPage({ ...EVERY_ANSWER, [MODELS]: () => json({ tiers: "no" }) });

    expect(container.textContent).toContain(UNREADABLE_ANSWER);
  });

  test("the page offers no control of its own, and Edit routing goes to the routing screen", async () => {
    // What breaks if this is deleted: a second editor for the chain, with a second copy of the
    // route's bounds, or an Edit routing action that goes nowhere.
    const { container } = await modelsPage(EVERY_ANSWER);

    expect(container.querySelectorAll("button, form, input")).toHaveLength(0);
    const edit = [...container.querySelectorAll("a")].filter((one) => one.textContent === "Edit routing");
    expect(edit.map((one) => one.getAttribute("href"))).toEqual([MATRIX_PATH]);
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
  });

  test("the spend window starts on the UTC day seven days before now", () => {
    // What breaks if this is deleted: a cost over a window a day longer or shorter than the one
    // the heading names, because the first day was taken in the browser's own time zone.
    const path = spendSinceApiPath("/report/spend", "department", new Date("2019-03-06T01:30:00Z"));

    expect(path).toBe("/report/spend?dimension=department&since=2019-02-27");
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.operate_routes` that this page
    // goes on reading, which renders as nothing on every card in production.
    const body = models();
    expect(Object.keys(body).sort()).toEqual(backendModelFields(ROUTES, "ModelsView").sort());
    const first = (key: string) => Object.keys((body[key] as Record<string, unknown>[])[0] ?? {}).sort();
    expect(first("tiers")).toEqual(backendModelFields(ROUTES, "TierView").sort());
    expect(first("lanes")).toEqual(backendModelFields(ROUTES, "LaneTrafficView").sort());
    expect(first("providers")).toEqual(backendModelFields(ROUTES, "ProviderView").sort());
    expect(first("unmeasured")).toEqual(backendModelFields(ROUTES, "UnmeasuredView").sort());
  });
});
