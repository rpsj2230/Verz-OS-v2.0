/**
 * The six Report pages rebuilt as dashboards: Usage, Spend, Adoption, Service levels, Quality and
 * canaries, Questions and gaps.
 *
 * **Each draws what the API sent and computes nothing it was not sent.** A total is the API's
 * field, printed even when it disagrees with the lines beside it, which no real response can,
 * because that is the only way to tell a printed field from a recomputed one. **A figure nothing
 * records is "Not recorded yet", never nought**: cost before any model is priced, tokens the ledger
 * does not count, the canaries' runs where none ran. **Nothing about a hidden row is drawn**: a
 * withheld reading or run renders as the markup of an install with none, and a full page says there
 * is more with no number in it. **People are named, never numbered**: an id reaches the export and
 * never the page.
 *
 * Mounted through the real route table and shell, signed in, with the stand-in API answering by
 * path from the page cases in `support/pageCases/`, overridden per test.
 *
 * Task ids: M27.7.14, M27.7.15, M27.7.16, M27.7.17, M27.7.18, M27.7.19, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED } from "../src/components/kit";
import { NOT_IN_THE_DIRECTORY } from "../src/pages/usageQuery";
import { usageSheets } from "../src/pages/reports/UsagePage";
import { spendSheets, NO_COST_YET, NOT_BUILT } from "../src/pages/reports/SpendPage";
import { MORE_DEPARTMENTS, NONE_QUIET } from "../src/pages/reports/AdoptionPage";
import { NOT_MEASURED, NO_LANES } from "../src/pages/reports/ServiceLevelsPage";
import { CUT_OFF, FINDINGS_GO_TO_THE_ALERT, NO_RUN_IN_PERIOD } from "../src/pages/reports/QualityPage";
import { SOURCE_NOT_NAMED } from "../src/pages/reports/QuestionsPage";
import { REPORT_PERIODS, PERIOD_LABEL } from "../src/pages/reports/reportParts";
import { daysBefore, spendReportPath } from "../src/pages/spendQuery";
import { serviceLevelsPathFor } from "../src/pages/serviceLevelsQuery";
import { qualityApiPathFor } from "../src/pages/qualityQuery";
import { questionsApiPathFor } from "../src/pages/questionsQuery";
import { usageApiPath } from "../src/pages/usageQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { declaredParameterSchema, declaredQueryParameters } from "./support/openapi";
import { PAGES } from "./support/pageCases";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const API = "/api/v1";
const USAGE = `${API}/report/usage`;
const SPEND = `${API}/report/spend`;
const ADOPTION = `${API}/report/adoption`;
const LEVELS = `${API}/report/service-levels`;
const QUALITY = `${API}/report/quality`;
const QUESTIONS = `${API}/report/questions`;

const ADDRESSES = ["/usage", "/spend", "/adoption", "/service-levels", "/quality", "/questions"] as const;

interface Mounted {
  readonly root: Element;
  /** Every API address asked, with its query, in order. */
  readonly asked: string[];
  /** The page's text, header included. */
  readonly text: () => string;
  /** The text under the header: the figures and the cards, without the period switch's digits. */
  readonly below: () => string;
  /** The page's markup with React's generated ids made alike, for comparing two renders. */
  readonly markup: () => string;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "x-trace-id": "trace-report" } });
}

/** The console at `address`, with the page case's answers changed by `changes`, once nothing loads. */
async function reportAt(address: string, changes: Readonly<Record<string, unknown>> = {}): Promise<Mounted> {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const answers: Readonly<Record<string, unknown>> = { ...(PAGES[address]?.answers ?? {}), ...changes };
  const asked: string[] = [];
  const idp = fakeIdentityProvider({
    api(url) {
      const parsed = new URL(url, "https://console.test");
      if (parsed.pathname.startsWith(`${API}/report/`)) {
        asked.push(`${parsed.pathname}${parsed.search}`);
      }
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(answers[NAVIGATION_ADDRESS] ?? COMPANY_CONSOLE);
      }
      return parsed.pathname in answers ? json(answers[parsed.pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  const root = (): Element => container.querySelector("main#main") ?? container;
  await settle(root);
  const page = (): Element | null => root().querySelector("[data-slot='report-page']");
  return {
    root: root(),
    asked,
    text: () => page()?.textContent ?? "",
    below: () =>
      [...(page()?.children ?? [])]
        .filter((one) => one.getAttribute("data-slot") !== "page-header")
        .map((one) => one.textContent ?? "")
        .join(" "),
    markup: () => (page()?.innerHTML ?? "").replace(/«r\w+»/g, "«id»"),
  };
}

async function settle(root: () => Element): Promise<void> {
  await waitFor(
    () => {
      expect(root().querySelector("[data-slot='report-page']")).not.toBeNull();
      expect(root().querySelector("[role='status']")).toBeNull();
    },
    { timeout: 10_000 },
  );
}

/** The value a figure card drew beside its label, or null when the card is not on the page. */
function figure(root: Element, label: string): string | null {
  for (const card of root.querySelectorAll("[data-slot='stat-card']")) {
    if (card.querySelector("dt")?.textContent === label) {
      const drawn = card.querySelector("dd > span")?.cloneNode(true) as Element | undefined;
      // The reason a figure is not recorded is read to a screen reader beside it, not drawn in it.
      drawn?.querySelectorAll(".sr-only").forEach((one) => {
        one.remove();
      });
      return drawn?.textContent ?? "";
    }
  }
  return null;
}

function usageBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    start: "2019-02-26T09:00:00Z",
    end: "2019-03-05T09:00:00Z",
    departments: [
      { department: "support", questions: 3, people: 2 },
      { department: "web", questions: 0, people: 0 },
    ],
    people: [
      { person: "u_ana_7f3a", questions: 2, name: "Ana Lim" },
      { person: "u_gone_9c1d", questions: 1, name: null },
    ],
    questions: 41,
    machine_included: false,
    not_measured: [],
    tokens: [
      {
        axis: "model",
        lines: [
          { key: "sonnet", runs: 2, tokens_in: 600, tokens_out: 100 },
          { key: "haiku", runs: 1, tokens_in: 500, tokens_out: 80 },
        ],
        total_runs: 7,
        total_tokens_in: 1250,
        total_tokens_out: 380,
      },
    ],
    ...over,
  };
}

function spendBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    dimension: "department",
    built: true,
    lines: [
      { key: "finance", cost_minor: 300 },
      { key: "support", cost_minor: 700 },
    ],
    machine_included: false,
    total_minor: 5500,
    as_of: "2019-03-04T09:00:00Z",
    freshness: "live",
    currency: "SGD",
    time_zone: "UTC",
    not_recorded: [],
    ...over,
  };
}

// ------------------------------------------------------------------------------ every page
describe("every Report page", () => {
  test.each(ADDRESSES)("%s offers the three periods, and choosing one asks for that window", async (address) => {
    // What breaks if this is deleted: a page's switch changes its words and not its request, so a
    // reader reads a week's figures under a heading that says ninety days.
    const page = await reportAt(address);
    const switches = page.root.querySelector(`[role='group'][aria-label='${PERIOD_LABEL}']`);
    const buttons = [...(switches?.querySelectorAll("button") ?? [])];

    expect(buttons.map((one) => one.textContent)).toEqual(REPORT_PERIODS.map((days) => `${String(days)} days`));
    const before = page.asked.length;
    const ninety = buttons.find((one) => one.textContent === "90 days");
    if (ninety === undefined) {
      throw new Error("No 90 days button.");
    }
    fireEvent.click(ninety);
    await waitFor(() => {
      expect(page.asked.length).toBeGreaterThan(before);
    });
    const latest = page.asked.slice(before).join(" ");
    const expected: Record<string, string> = {
      "/usage": "days=90",
      "/adoption": "days=90",
      "/quality": "days=90",
      "/questions": "days=90",
      "/service-levels": `hours=${String(90 * 24)}`,
      "/spend": "since=",
    };
    expect(latest).toContain(expected[address]);
    expect(ninety.getAttribute("aria-pressed")).toBe("true");
  });

  test("every period is inside the window each route admits, and each request names only what the route declares", () => {
    // What breaks if this is deleted: a period past a route's bound is refused with a validation
    // error on every load, or a parameter is renamed on the route, the console keeps sending the
    // old one, FastAPI discards it, and the page shows the default window under another's name.
    const widest = Math.max(...REPORT_PERIODS);
    for (const [route, name, limit] of [
      [USAGE, "days", widest],
      [ADOPTION, "days", widest],
      [QUALITY, "days", widest],
      [QUESTIONS, "days", widest],
      [LEVELS, "hours", widest * 24],
    ] as const) {
      expect(declaredParameterSchema(route, "get", name)["maximum"] as number, route).toBeGreaterThanOrEqual(limit);
    }
    const now = new Date("2019-03-31T23:30:00Z");
    for (const [route, path] of [
      [USAGE, usageApiPath(90)],
      [QUALITY, qualityApiPathFor(90)],
      [QUESTIONS, questionsApiPathFor(90)],
      [LEVELS, serviceLevelsPathFor(90)],
      [SPEND, spendReportPath("model", 90, now)],
    ] as const) {
      const declared = new Set(declaredQueryParameters(route, "get"));
      const sent = [...new URL(path, "https://console.test").searchParams.keys()];
      expect(sent.length, route).toBeGreaterThan(0);
      expect(sent.filter((one) => !declared.has(one)), route).toEqual([]);
    }
    expect(daysBefore(now, 30)).toBe("2019-03-01");
  });
});

// ------------------------------------------------------------------------------------ usage
describe("Usage", () => {
  test("the figures are the API's totals, never sums of the lines drawn", async () => {
    // What breaks if this is deleted: the page adds the lines up, and the day a table is bounded
    // the figure on screen stops being the one the API stands behind. The fixture's totals
    // disagree with its lines, which no real response can.
    const page = await reportAt("/usage", { [USAGE]: usageBody() });

    expect(figure(page.root, "Questions")).toBe("41");
    expect(figure(page.root, "Tokens in")).toBe("1,250");
    expect(figure(page.root, "Tokens out")).toBe("380");
    expect(page.text()).toContain("Total 1,250 in, 380 out, over 7 requests with a model call.");
    expect(page.text()).not.toContain("1,100");
  });

  test("people are named, somebody gone from the directory is said so, and no id reaches the page", async () => {
    // What breaks if this is deleted: the usage table goes back to principal ids, which the owner
    // found cluttered, or an unnamed person is dropped from the list their questions are in.
    const page = await reportAt("/usage", { [USAGE]: usageBody() });

    expect(page.text()).toContain("Ana Lim");
    expect(page.text()).toContain(NOT_IN_THE_DIRECTORY);
    expect(page.text()).not.toMatch(/u_ana_7f3a|u_gone_9c1d/);
    const people = usageSheets(usageBody() as never, 30).find((one) => one.filename.includes("by-person"));
    expect(people?.csv()).toContain("u_gone_9c1d");
  });

  test("tokens the ledger does not count read Not recorded yet, and no zero is drawn for them", async () => {
    // What breaks if this is deleted: an install that counts no tokens shows 0 in and 0 out, which
    // says nobody's question used any.
    const page = await reportAt("/usage", { [USAGE]: usageBody({ tokens: [], not_measured: ["tokens"] }) });

    expect(figure(page.root, "Tokens in")).toBe(NOT_RECORDED);
    expect(figure(page.root, "Tokens out")).toBe(NOT_RECORDED);
  });

  test("a reader offered nothing is shown no figure, whatever the body carries beside it", async () => {
    // What breaks if this is deleted: a reader holding no usage grant is shown a zero, which is a
    // count the API never sent them, or a heading for a table they were not offered.
    const page = await reportAt("/usage", {
      [USAGE]: usageBody({ departments: null, people: null, questions: null, tokens: [], hidden: 12 }),
    });

    expect(page.root.querySelector("[data-slot='stat-card']")).toBeNull();
    expect(page.below()).not.toMatch(/[0-9]/);
  });
});

// ------------------------------------------------------------------------------------ spend
describe("Spend", () => {
  test("cost the install does not record reads Not recorded yet with the report's reason, and draws no 0.00", async () => {
    // What breaks if this is deleted: every install nobody has priced shows 0.00 as a measurement,
    // on the screen somebody reads before deciding not to worry.
    const why = "no model has a price in this install's currency yet";
    const page = await reportAt("/spend", {
      [SPEND]: spendBody({ lines: [], total_minor: 0, not_recorded: [{ figure: "cost", why }] }),
    });

    expect(figure(page.root, "Cost")).toBe(NOT_RECORDED);
    expect(page.text()).toContain(NO_COST_YET);
    expect(page.text()).toContain("No model has a price in this install's currency yet.");
    expect(page.text()).not.toContain("0.00");
    expect(spendSheets(spendBody({ not_recorded: [{ figure: "cost", why }] }) as never, 30)).toEqual([]);
  });

  test("recorded cost prints the API's total and draws the lines largest first", async () => {
    // What breaks if this is deleted: the total is added up here, or the bars are drawn in an
    // order that hides the largest line below the fold.
    const page = await reportAt("/spend", { [SPEND]: spendBody() });

    expect(figure(page.root, "Cost")).toBe("SGD 55.00");
    const labels = [...page.root.querySelectorAll("[data-slot='bar-list'] tbody th")].map((one) => one.textContent);
    expect(labels).toEqual(["support", "finance"]);
    expect(page.text()).not.toContain("10.00");
  });

  test("a report nobody has built says so and draws no figure", async () => {
    // What breaks if this is deleted: a fresh install's unbuilt report reads as a company that
    // spent nothing.
    const page = await reportAt("/spend", {
      [SPEND]: spendBody({ built: false, lines: [], total_minor: null, as_of: null, freshness: "unstated" }),
    });

    expect(page.text()).toContain(NOT_BUILT);
    expect(page.text()).not.toContain("0.00");
  });
});

// --------------------------------------------------------------------------------- adoption
describe("Adoption", () => {
  test("a department that asked nothing keeps its line and is listed as quiet", async () => {
    // What breaks if this is deleted: the zero lines are tidied away, and the departments that
    // stopped using the system vanish from the one page meant to show them.
    const page = await reportAt("/adoption", {
      [ADOPTION]: {
        items: [
          { department: "finance", questions: 0, people: 0 },
          { department: "support", questions: 12, people: 3 },
        ],
        next_cursor: null,
        truncated: false,
      },
      [USAGE]: usageBody(),
    });

    const rows = [...page.root.querySelectorAll("[data-slot='entity-table'] tbody tr")].map((row) =>
      [...row.querySelectorAll("td")].map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ["finance", "0", "0"],
      ["support", "12", "3"],
    ]);
    expect(page.root.querySelector("ul[aria-label='Quiet departments']")?.textContent).toBe("web");
    expect(figure(page.root, "Quiet departments")).toBe("1");
    expect(page.text()).not.toContain(NONE_QUIET);
  });

  test("a full page says there is more and never how many", async () => {
    // What breaks if this is deleted: a count arrives beside a bounded listing and the reader
    // learns the size of a set they were shown part of.
    const page = await reportAt("/adoption", {
      [ADOPTION]: { items: [{ department: "support", questions: 1, people: 1 }], next_cursor: "c", total: 47, truncated: true },
    });

    expect(page.text()).toContain(MORE_DEPARTMENTS);
    expect(MORE_DEPARTMENTS).not.toMatch(/[0-9]/);
    expect(page.text()).not.toContain("47");
  });
});

// --------------------------------------------------------------------------- service levels
describe("Service levels", () => {
  test("a reading with no lanes renders exactly as one carrying fields about what it withheld", async () => {
    // What breaks if this is deleted: something upstream adds a flag saying a reading was narrowed,
    // a generous renderer draws it, and "you may not be told" becomes distinguishable from
    // "there is nothing to tell".
    const bare = await reportAt("/service-levels", { [LEVELS]: { start: "2019-03-04T09:00:00Z", end: "2019-03-05T09:00:00Z", lanes: [] } });
    const bareMarkup = bare.markup();
    const leaky = await reportAt("/service-levels", {
      [LEVELS]: { start: "2019-03-04T09:00:00Z", end: "2019-03-05T09:00:00Z", lanes: [], narrowed: true, hidden: 4 },
    });

    expect(leaky.markup()).toBe(bareMarkup);
    expect(leaky.text()).toContain(NO_LANES);
    expect(leaky.text()).not.toMatch(/grant|permission|scope|narrow|withheld|hidden/i);
  });

  test("a figure the sample could not support reads Not measured, never nought", async () => {
    // What breaks if this is deleted: a quiet lane shows a p95 of 0 ms and a success rate of 0%,
    // which reads as an outage.
    const page = await reportAt("/service-levels", {
      [LEVELS]: {
        start: "2019-03-04T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        lanes: [
          { lane: "task", objective_p95_ms: 2000, objective_success_rate: 0.99, p95_ms: null, success_rate: null, requests: 0, met: false, shortfalls: [] },
        ],
      },
    });

    const cells = [...page.root.querySelectorAll("[data-slot='entity-table'] tbody td")].map((one) => one.textContent);
    expect(cells[2]).toBe(NOT_MEASURED);
    expect(cells[4]).toBe(NOT_MEASURED);
    expect(page.below()).not.toMatch(/(^|[^0-9])0 ms/);
    expect(page.below()).not.toMatch(/(^|[^0-9.])0\.0%/);
  });
});

// ---------------------------------------------------------------------------------- quality
describe("Quality and canaries", () => {
  const quiet = {
    last_canary_run: null,
    canaries_owed: true,
    canaries_started: true,
    canary_interval_seconds: 43200,
    findings_are_recorded: false,
    evaluation_runs_are_recorded: false,
    runs: [],
    runs_truncated: false,
  };

  test("a withheld run renders exactly as an install whose canaries never ran, with no zero", async () => {
    // What breaks if this is deleted: a reader who may not see a run can tell from the page that
    // one happened, or reads "Passed 0" for a period in which nothing was recorded for them.
    const none = await reportAt("/quality", { [QUALITY]: quiet });
    const noneMarkup = none.markup();
    const withheld = await reportAt("/quality", { [QUALITY]: { ...quiet, hidden_runs: 3, withheld: true } });

    expect(withheld.markup()).toBe(noneMarkup);
    expect(figure(withheld.root, "Runs in this period")).toBe(NOT_RECORDED);
    expect(withheld.text()).toContain(NO_RUN_IN_PERIOD);
    expect(figure(withheld.root, "Passed")).toBeNull();
  });

  test("the runs listed are counted, a cut-off list says so, and nothing a run found is on the page", async () => {
    // What breaks if this is deleted: a pass is drawn for a run the API did not call passed, a
    // count past the bound is printed as exact, or a finding arrives on a page nobody decided.
    const run = (at: string, state: string) => ({ started_at: at, finished_at: at, state });
    const page = await reportAt("/quality", {
      [QUALITY]: {
        ...quiet,
        last_canary_run: run("2019-03-05T06:00:00Z", "failed"),
        runs: [run("2019-03-05T06:00:00Z", "failed"), run("2019-03-04T18:00:00Z", "passed"), run("2019-03-04T06:00:00Z", "passed")],
        runs_truncated: true,
        finding: "SECRET-FIELD",
      },
    });

    expect(figure(page.root, "Last run")).toBe("Failed");
    expect(figure(page.root, "Passed")).toBe("2+");
    expect(figure(page.root, "Failed")).toBe("1+");
    expect(page.text()).toContain(CUT_OFF);
    expect(page.text()).toContain(FINDINGS_GO_TO_THE_ALERT);
    expect(page.text()).not.toContain("SECRET-FIELD");
  });
});

// -------------------------------------------------------------------------------- questions
describe("Questions and gaps", () => {
  test("the figures are sums of the lines sent, and a source the reader is not told is never counted as one", async () => {
    // What breaks if this is deleted: a hidden source is counted among the sources to connect,
    // which is a count of something the reader was not shown.
    const page = await reportAt("/questions", {
      [QUESTIONS]: {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [
          { department: "support", source: "xero", asked: 5 },
          { department: "support", source: null, asked: 2 },
          { department: "web", source: "xero", asked: 1 },
        ],
        nothing_connected: false,
        answered_when_nothing_connected: "Nothing I can reach is connected to that yet.",
        answered_when_nothing_found: "I could not find that.",
        unanswered_are_recorded: false,
      },
    });

    expect(figure(page.root, "Unanswered questions")).toBe("8");
    expect(figure(page.root, "Departments asking")).toBe("2");
    expect(figure(page.root, "Sources to connect")).toBe("1");
    expect(page.text()).toContain(SOURCE_NOT_NAMED);
    expect(page.text()).not.toContain("Nothing I can reach");
  });
});
