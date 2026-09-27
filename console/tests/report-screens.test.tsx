/**
 * The Usage and cost, Questions and gaps, and Quality and canaries screens: what each draws, what
 * each refuses to draw, and what each says instead.
 *
 * All three stand on ledgers that hold less than `docs/screens.html` draws, so the failures worth
 * testing are the ones that look like the design working. A token column of zeros looks like the
 * usage the design asks for and says nobody used any tokens, and a token total added up in the
 * browser looks like the API's and is a figure nobody can reconcile; a gaps table with question shapes
 * blank looks like the design's card and says every question was answered; a green canary line
 * looks like the design's card and says a run passed that nothing checked. Each is asserted
 * against over the rendered page.
 *
 * **What the API sends is compared with the Python models, not with this file's copy of them.**
 * `tests/support/python.ts` reads the field names out of `brain.report_routes`, and the window this
 * console asks for is read against the route's own declared bound.
 *
 * **The pages are rendered directly**, inside a router holding only their own paths, because the
 * route table and the navigation are wired by a separate change. The phone cases are written up
 * for `tests/phone-width.test.tsx` beside that wiring.
 *
 * **Loading, empty, unreachable and failed are four different sentences on each page**, which is
 * `docs/admin-console.md`'s rule, and each page is held to all four.
 *
 * Task ids: M27.7.14, M27.7.18, M27.7.19
 */

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import {
  CANARIES_HEADING,
  FINDINGS_ARE_NOT_RECORDED,
  GOLDEN_NOT_ON_AN_INSTALL,
  NOTHING_ACTS_ON_A_RESULT,
  NOT_ON_AN_INSTALL,
  NO_EVALUATION_RUN,
  NO_RUN,
  QUALITY_HEADING,
  Quality,
  notStarted,
} from "../src/pages/Quality";
import { QUALITY_API_PATH, cadence, readQuality, runLine } from "../src/pages/qualityQuery";
import {
  CONNECT_A_SOURCE,
  EXPORT_NOT_OFFERED,
  NO_GAP,
  NO_SOURCE,
  QUESTIONS_HEADING,
  Questions,
  UNANSWERED_ARE_NOT_RECORDED,
  UNANSWERED_HEADING,
  WORDS_ARE_NOT_KEPT,
  notFoundIsNotAGap,
} from "../src/pages/Questions";
import { QUESTIONS_API_PATH, readQuestions } from "../src/pages/questionsQuery";
import { THE_BRAIN_COULD_NOT_BE_REACHED as COULD_NOT_REACH_THE_BRAIN } from "../src/ui/FailureNotice";
import {
  NOBODY_ASKED,
  NOTHING_TO_SHOW,
  NO_PERSON_MATCHES,
  TOKENS_ARE_OVER_MODEL_CALLS,
  USAGE_HEADING,
  Usage,
  WITHOUT_AUTOMATION,
  WITH_AUTOMATION,
} from "../src/pages/Usage";
import {
  EVERYBODY,
  NOT_MEASURED_SENTENCES,
  NO_MODEL_CALL,
  PEOPLE_PER_PAGE,
  PERIODS,
  RUNS_HEADING,
  USAGE_API_PATH,
  glanceTokens,
  glanceTokensLine,
  notMeasuredSentence,
  peoplePage,
  readUsage,
  tokensHeading,
  usageApiPath,
  type PersonUsageRow,
} from "../src/pages/usageQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterSchema } from "./support/openapi";
import { backendModelFields } from "./support/python";

const ROUTES = "src/brain/report_routes.py";
const API = "/api/v1";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/**
 * One token breakdown in the shape `brain.report_routes.TokenBreakdownView` serialises.
 *
 * The totals disagree with the lines on purpose, which no real response can: a page that adds the
 * lines up draws 3 runs, 1100 in and 180 out where the API said 7, 1250 and 380.
 */
function breakdown(
  axis: string,
  keys: readonly [string, string],
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    axis,
    lines: [
      { key: keys[0], runs: 2, tokens_in: 600, tokens_out: 100 },
      { key: keys[1], runs: 1, tokens_in: 500, tokens_out: 80 },
    ],
    total_runs: 7,
    total_tokens_in: 1250,
    total_tokens_out: 380,
    ...over,
  };
}

/** One breakdown per axis, in the order the API sends them. */
function everyAxis(): Record<string, unknown>[] {
  return [
    breakdown("person", [sentinel("ana"), sentinel("ben")]),
    breakdown("department", [sentinel("support"), sentinel("web")]),
    breakdown("model", [sentinel("sonnet"), "no single model"]),
    breakdown("agent", [sentinel("quote-helper"), "no agent"]),
  ];
}

function usageBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    start: "2019-02-26T09:00:00Z",
    end: "2019-03-05T09:00:00Z",
    departments: [
      { department: sentinel("support"), questions: 3, people: 2 },
      { department: sentinel("web"), questions: 1, people: 1 },
    ],
    people: [
      { person: sentinel("ana"), questions: 2 },
      { person: sentinel("ben"), questions: 1 },
      { person: sentinel("cai"), questions: 1 },
    ],
    questions: 4,
    machine_included: false,
    not_measured: [],
    tokens: everyAxis(),
    ...over,
  };
}

function questionsBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    nothing_connected: true,
    answered_when_nothing_connected: sentinel("nothing-connected"),
    answered_when_nothing_found: sentinel("nothing-found"),
    unanswered_are_recorded: false,
    ...over,
  };
}

function qualityBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    last_canary_run: {
      started_at: "2019-03-05T06:00:00Z",
      finished_at: "2019-03-05T06:02:00Z",
      state: "finished",
    },
    canaries_started: false,
    canary_interval_seconds: 43200,
    findings_are_recorded: false,
    evaluation_runs_are_recorded: false,
    ...over,
  };
}

/** A stand-in API answering one path with one body, or with a refusal, or not at all. */
function answering(path: string, body: unknown, status = 200): FakeIdp {
  return fakeIdentityProvider({
    api(url) {
      if (!new URL(url, "https://console.test").pathname.endsWith(`${API}${path}`)) {
        return null;
      }
      return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    },
  });
}

/** A stand-in API that the request never reaches, which is what a lost network looks like. */
function unreachable(): FakeIdp {
  return fakeIdentityProvider({
    api(url) {
      if (url.includes(`${API}/report/`)) {
        throw new TypeError("Failed to fetch");
      }
      return null;
    },
  });
}

/** The three pages, each at its own address. */
function Pages() {
  return (
    <Routes>
      <Route path="/usage" element={<Usage />} />
      <Route path="/questions" element={<Questions />} />
      <Route path="/quality" element={<Quality />} />
    </Routes>
  );
}

/** Mount one page at one address, against a stand-in API, and wait for it to settle. */
async function mount(address: string, idp: FakeIdp): Promise<HTMLElement> {
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { container } = render(
    <MemoryRouter initialEntries={[address]}>
      <Pages />
    </MemoryRouter>,
  );
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return container;
}

function text(container: HTMLElement): string {
  return container.textContent ?? "";
}

function page(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>("article.page");
  if (!found) {
    throw new Error("No page was rendered.");
  }
  return found;
}

/** The text of one row of a figures list, read under its own label. */
function field(container: HTMLElement, label: string): string {
  const term = [...container.querySelectorAll("dt")].find((one) => one.textContent === label);
  if (!term) {
    throw new Error(`No row labelled ${label}.`);
  }
  return term.nextElementSibling?.textContent ?? "";
}

/** The totals row of one captioned table, cell by cell. */
function totals(container: HTMLElement, caption: string): string[] {
  const table = [...container.querySelectorAll("table")].find(
    (one) => one.querySelector("caption")?.textContent === caption,
  );
  if (!table) {
    throw new Error(`No table captioned ${caption}.`);
  }
  return [...table.querySelectorAll("tfoot tr th, tfoot tr td")].map((cell) => cell.textContent ?? "");
}

/** Every cell of one captioned table, row by row. */
function cells(container: HTMLElement, caption: string): string[][] {
  const table = [...container.querySelectorAll("table")].find(
    (one) => one.querySelector("caption")?.textContent === caption,
  );
  if (!table) {
    throw new Error(`No table captioned ${caption}.`);
  }
  return [...table.querySelectorAll("tbody tr")].map((row) =>
    [...row.querySelectorAll("th, td")].map((cell) => cell.textContent ?? ""),
  );
}

// --- the four states, on every page ------------------------------------------------------------

describe("every Report screen here", () => {
  const screens = [
    { address: "/usage", path: USAGE_API_PATH, heading: USAGE_HEADING, body: usageBody() },
    {
      address: "/questions",
      path: QUESTIONS_API_PATH,
      heading: QUESTIONS_HEADING,
      body: questionsBody(),
    },
    { address: "/quality", path: QUALITY_API_PATH, heading: QUALITY_HEADING, body: qualityBody() },
  ];

  test.each(screens)(
    "$heading says loading while it asks, and then stops saying it",
    async ({ address, path, heading, body }) => {
      // What breaks if this is deleted: a blank panel while the request is in flight, or a
      // loading sentence left on the page after the answer arrived.
      const idp = answering(path, body);
      const loaded = await loadConsole({ idp });
      await signIn(loaded);
      const { container } = render(
        <MemoryRouter initialEntries={[address]}>
          <Pages />
        </MemoryRouter>,
      );

      expect(container.querySelector("h1")?.textContent).toBe(heading);
      expect(container.querySelector('p.note[role="status"]')?.textContent).toBe("Loading.");
      await waitFor(() => {
        if (container.textContent?.includes("Loading.")) {
          throw new Error("still loading");
        }
      });
    },
  );

  test.each(screens)(
    "$heading tells a request the API refused apart from one that never reached it",
    async ({ address, path }) => {
      // What breaks if this is deleted: a lost network and a fault on the server read as one
      // sentence, and the person who could fix one is sent to fix the other.
      const failed = await mount(
        address,
        answering(path, { message: sentinel("fault"), trace_id: "t-fault" }, 500),
      );
      expect(text(failed)).toContain(SOMETHING_DID_NOT_WORK);
      expect(text(failed)).toContain(sentinel("fault"));
      expect(text(failed)).not.toContain(COULD_NOT_REACH_THE_BRAIN);

      const lost = await mount(address, unreachable());
      expect(text(lost)).toContain(COULD_NOT_REACH_THE_BRAIN);
      expect(text(lost)).not.toContain(SOMETHING_DID_NOT_WORK);
    },
  );

  test.each(screens)(
    "$heading shows a refusal in the API's own words and explains nothing",
    async ({ address, path }) => {
      // What breaks if this is deleted: a 404 explained as a permission problem, which tells a
      // caller the screen exists and they are not allowed it.
      const container = await mount(
        address,
        answering(path, { message: sentinel("refusal"), trace_id: "t-1" }, 404),
      );

      // Read inside the notice, because the Quality screen's own lede names the permission
      // canaries and a page-wide search would be satisfied by that rather than by the refusal.
      const notice = container.querySelector(".notice");
      expect(notice?.textContent).toContain(sentinel("refusal"));
      expect(notice?.innerHTML).not.toMatch(/permission|grant|allowed|denied/i);
      expect(container.querySelector("table")).toBeNull();
      expect(page(container).querySelectorAll("section")).toHaveLength(0);
    },
  );
});

// --- Usage and cost ----------------------------------------------------------------------------

describe("the Usage and cost screen", () => {
  test("every field the API sends is read, and the page reads nothing it does not send", () => {
    // What breaks if this is deleted: a field added to the usage response arrives and is dropped by
    // `readUsage`, or the page reads a field the route no longer sends and draws nothing silently.
    expect(backendModelFields(ROUTES, "UsageView").sort()).toEqual(
      ["start", "end", "departments", "people", "questions", "machine_included", "not_measured", "tokens"].sort(),
    );
    expect(Object.keys(usageBody()).sort()).toEqual(backendModelFields(ROUTES, "UsageView").sort());
    expect(backendModelFields(ROUTES, "DepartmentUsageView")).toEqual([
      "department",
      "questions",
      "people",
    ]);
    expect(backendModelFields(ROUTES, "PersonUsageView")).toEqual(["person", "questions"]);
    const [first] = everyAxis();
    expect(Object.keys(first ?? {}).sort()).toEqual(backendModelFields(ROUTES, "TokenBreakdownView").sort());
    expect(Object.keys((first?.["lines"] as Record<string, unknown>[])[0] ?? {}).sort()).toEqual(
      backendModelFields(ROUTES, "TokenLineView").sort(),
    );
  });

  test("every period offered is inside the window the route admits", () => {
    // What breaks if this is deleted: choosing a period becomes a 422, which reaches a person as
    // the least useful sentence this console has. Read off the route's own parameter.
    const days = declaredParameterSchema(`${API}${USAGE_API_PATH}`, "get", "days");

    for (const period of PERIODS) {
      expect(period).toBeGreaterThanOrEqual(days["minimum"] as number);
      expect(period).toBeLessThanOrEqual(days["maximum"] as number);
    }
    expect(PERIODS[0]).toBe(days["default"]);
    expect(usageApiPath(30)).toBe("/report/usage?days=30");
  });

  test("draws both tables as sent, with the API's total and never one added up here", async () => {
    // What breaks if this is deleted: a line dropped, a column lost, or a total recomputed from the
    // lines, which is the renderer that will one day print a figure nobody can reconcile. The body's
    // total disagrees with its lines on purpose, which no real response can.
    const container = await mount(
      "/usage",
      answering(USAGE_API_PATH, usageBody({ questions: 999 })),
    );

    expect(cells(container, "Questions by department")).toEqual([
      [sentinel("support"), "3", "2"],
      [sentinel("web"), "1", "1"],
    ]);
    expect(cells(container, "Questions by person")).toEqual([
      [sentinel("ana"), "2"],
      [sentinel("ben"), "1"],
      [sentinel("cai"), "1"],
    ]);
    const glance = container.querySelector('[aria-label="Usage at a glance"]');
    expect(glance?.textContent).toContain("999");
    expect(glance?.textContent).not.toContain("4");
  });

  test("a measure the API still names as not measured is a sentence, and no column or zero is drawn for it", async () => {
    // What breaks if this is deleted: a token column of zeros, which says nobody used any tokens,
    // on the day the ledger stops filling a field and the API names it again.
    const container = await mount(
      "/usage",
      answering(USAGE_API_PATH, usageBody({ not_measured: ["tokens", "model", "agent"], tokens: [] })),
    );

    for (const measure of ["tokens", "model", "agent"]) {
      expect(text(container)).toContain(notMeasuredSentence(measure));
    }
    const headers = [...container.querySelectorAll("th[scope=col]")].map((one) => one.textContent);
    expect(headers).toEqual(["Department", "Questions", "People", "Person", "Questions"]);
  });

  test("no not-measured sentence says that nothing calls a model", () => {
    // What breaks if this is deleted: the sentences going on telling an administrator no model is
    // called on an install whose ledger meters every call, which is what they said until the
    // executor started calling one.
    for (const sentence of Object.values(NOT_MEASURED_SENTENCES)) {
      expect(sentence).not.toMatch(/nothing calls a model|no request has been answered by a model|yet\b/i);
    }
  });

  test("a measure the API does not name is not mentioned, and a withheld axis has no token card", async () => {
    // What breaks if this is deleted: the page draws a By agent or Tokens by agent card for a reader
    // the API did not offer the agent axis, which tells them there is one.
    const container = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({ not_measured: ["model"], tokens: everyAxis().filter((one) => one["axis"] !== "agent") }),
      ),
    );

    const headings = [...container.querySelectorAll("h2")].map((one) => one.textContent);
    expect(text(container)).not.toContain(notMeasuredSentence("agent"));
    expect(headings).not.toContain("By agent");
    expect(headings).not.toContain(tokensHeading("agent"));
    expect(headings).toContain(tokensHeading("model"));
    expect(text(container)).not.toMatch(/withheld|hidden|not shown/i);
  });

  test("each token breakdown is a table of the lines sent, with the API's totals and never a sum made here", async () => {
    // What breaks if this is deleted: a line dropped, the runs column called questions, or a totals
    // row added up from the lines, which is a figure nobody can reconcile. The body's totals
    // disagree with its lines on purpose.
    const container = await mount("/usage", answering(USAGE_API_PATH, usageBody()));

    expect([...container.querySelectorAll("h2")].map((one) => one.textContent)).toEqual([
      "At a glance",
      "By department",
      "By person",
      tokensHeading("person"),
      tokensHeading("department"),
      tokensHeading("model"),
      tokensHeading("agent"),
    ]);
    expect(cells(container, tokensHeading("model"))).toEqual([
      [sentinel("sonnet"), "2", "600", "100"],
      ["no single model", "1", "500", "80"],
    ]);
    expect(cells(container, tokensHeading("agent"))[1]).toEqual(["no agent", "1", "500", "80"]);
    for (const axis of ["person", "department", "model", "agent"]) {
      expect(totals(container, tokensHeading(axis))).toEqual(["Total", "7", "1250", "380"]);
    }
    const table = [...container.querySelectorAll("table")].find(
      (one) => one.querySelector("caption")?.textContent === tokensHeading("person"),
    );
    expect([...(table?.querySelectorAll("th[scope=col]") ?? [])].map((one) => one.textContent)).toEqual([
      "Person",
      RUNS_HEADING,
      "Tokens in",
      "Tokens out",
    ]);
    expect(text(container)).not.toMatch(/1100|180\b/);
  });

  test("a breakdown with no lines says no question called a model, and draws no table of zeros", async () => {
    // What breaks if this is deleted: an empty token breakdown drawn as a table whose only row is a
    // total of zeros, or as a heading over nothing, which reads as a table somebody hid.
    const container = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({
          tokens: [breakdown("person", ["a", "b"], { lines: [], total_runs: 0, total_tokens_in: 0, total_tokens_out: 0 })],
        }),
      ),
    );

    const section = [...container.querySelectorAll("section")].find(
      (one) => one.querySelector("h2")?.textContent === tokensHeading("person"),
    );
    expect(section?.textContent).toBe(`${tokensHeading("person")}${NO_MODEL_CALL}`);
    expect(section?.querySelector("table")).toBeNull();
  });

  test("the at-a-glance tokens are the first breakdown's totals, and absent when there is no breakdown", async () => {
    // What breaks if this is deleted: the glance adding every breakdown's totals together, which
    // counts each token once per axis, or a tokens row of zeros for a reader offered no breakdown.
    const firstDiffers = [
      breakdown("department", ["d", "e"], { total_tokens_in: 3210, total_tokens_out: 765 }),
      ...everyAxis().slice(2),
    ];
    const container = await mount("/usage", answering(USAGE_API_PATH, usageBody({ tokens: firstDiffers })));
    expect(field(container, "Tokens")).toBe(`${glanceTokensLine(3210, 765)}${TOKENS_ARE_OVER_MODEL_CALLS}`);
    expect(glanceTokens([])).toBeNull();

    const none = await mount("/usage", answering(USAGE_API_PATH, usageBody({ tokens: [] })));
    expect([...none.querySelectorAll("dt")].map((one) => one.textContent)).not.toContain("Tokens");
  });

  test("whether automation was counted is drawn from the response", async () => {
    // What breaks if this is deleted: the page states its own assumption, and the day the API
    // counts automation the page goes on saying it does not.
    const without = await mount("/usage", answering(USAGE_API_PATH, usageBody()));
    expect(text(without)).toContain(WITHOUT_AUTOMATION);

    const withIt = await mount(
      "/usage",
      answering(USAGE_API_PATH, usageBody({ machine_included: true })),
    );
    expect(text(withIt)).toContain(WITH_AUTOMATION);
  });

  test("a reader offered no table sees one sentence and no figure, whatever else the body carries", async () => {
    // What breaks if this is deleted: a zero drawn for a reader holding no usage grant, or a field
    // added upstream to say what was withheld reaching the page. The bare body and a leaky one must
    // render the same markup.
    const bare = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({ departments: null, people: null, questions: null, not_measured: [], tokens: [] }),
      ),
    );
    const leaky = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({
          departments: null,
          people: null,
          questions: null,
          not_measured: [],
          tokens: [],
          hidden: 41,
          withheld_departments: [sentinel("elsewhere")],
        }),
      ),
    );

    expect(text(bare)).toContain(NOTHING_TO_SHOW);
    expect(page(bare).querySelectorAll("section")).toHaveLength(0);
    expect(page(leaky).innerHTML).toBe(page(bare).innerHTML);
    expect(text(leaky)).not.toMatch(/41|ELSEWHERE/);
  });

  test("a reader offered a token axis and no question table sees that table and no question figure", async () => {
    // What breaks if this is deleted: a reader the API gave only the model axis told there is
    // nothing to show, or shown "Questions 0" for a count the API withheld from them.
    const container = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({ departments: null, people: null, questions: null, tokens: [everyAxis()[2]] }),
      ),
    );

    expect(text(container)).not.toContain(NOTHING_TO_SHOW);
    expect([...container.querySelectorAll("dt")].map((one) => one.textContent)).toEqual(["Tokens", "Cost"]);
    expect(totals(container, tokensHeading("model"))).toEqual(["Total", "7", "1250", "380"]);
  });

  test("a period in which nobody asked draws zero lines and says nobody asked", async () => {
    // What breaks if this is deleted: an empty person table reads as a missing screen, or the
    // empty state and the no-grant state collapse into one sentence.
    const container = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({
          departments: [{ department: "support", questions: 0, people: 0 }],
          people: [],
          questions: 0,
        }),
      ),
    );

    expect(text(container)).toContain(NOBODY_ASKED);
    expect(text(container)).not.toContain(NOTHING_TO_SHOW);
    expect(cells(container, "Questions by department")).toEqual([["support", "0", "0"]]);
  });

  test("choosing a period asks for that window", async () => {
    // What breaks if this is deleted: the period control changes its label and asks for nothing.
    const idp = answering(USAGE_API_PATH, usageBody());
    const container = await mount("/usage", idp);

    fireEvent.change(container.querySelector("#usage-period") as HTMLSelectElement, {
      target: { value: "90" },
    });
    await waitFor(() => {
      if (!idp.urls.some((url) => url.endsWith("/report/usage?days=90"))) {
        throw new Error("the ninety-day window was not asked for");
      }
    });
    expect(idp.urls.some((url) => url.endsWith("/report/usage?days=7"))).toBe(true);
  });

  test("the person table pages, searches and orders the lines it was sent", async () => {
    // What breaks if this is deleted: a long list with no way through it, or a search that reads
    // as a search of the company rather than of the lines on the page.
    // Capitals in the reference and none in the search, so a comparison that lowers only one
    // side finds nothing. A person's reference is whatever the directory holds.
    const many = Array.from({ length: PEOPLE_PER_PAGE + 5 }, (_, at) => ({
      person: `U_${String(at).padStart(2, "0")}`,
      questions: 100 - at,
    }));
    const container = await mount(
      "/usage",
      answering(
        USAGE_API_PATH,
        usageBody({ people: many, questions: many.reduce((a, b) => a + b.questions, 0) }),
      ),
    );

    expect(cells(container, "Questions by person")).toHaveLength(PEOPLE_PER_PAGE);
    const [previous, next] = [
      ...container.querySelectorAll(".grid__pager button"),
    ] as HTMLButtonElement[];
    expect(previous?.disabled).toBe(true);
    fireEvent.click(next as HTMLButtonElement);
    expect(cells(container, "Questions by person")).toHaveLength(5);
    expect(text(container)).toContain("Page 2");

    fireEvent.change(container.querySelector("#usage-person-search") as HTMLInputElement, {
      target: { value: "u_03" },
    });
    expect(cells(container, "Questions by person")).toEqual([["U_03", "97"]]);

    fireEvent.change(container.querySelector("#usage-person-search") as HTMLInputElement, {
      target: { value: "nobody-matches" },
    });
    expect(text(container)).toContain(NO_PERSON_MATCHES);
    expect(text(container)).not.toContain(NOBODY_ASKED);
  });

  test("paging clamps, orders stably by reference, and never invents a line", () => {
    // What breaks if this is deleted: a page past the end draws an empty table that reads as
    // nobody matching, or the reference order moves between two readings of one list.
    const lines: PersonUsageRow[] = [
      { person: "u_b", questions: 3 },
      { person: "u_c", questions: 2 },
      { person: "u_a", questions: 1 },
    ];

    expect(peoplePage(lines, EVERYBODY).rows.map((one) => one.person)).toEqual([
      "u_b",
      "u_c",
      "u_a",
    ]);
    expect(
      peoplePage(lines, { ...EVERYBODY, sort: "person" }).rows.map((one) => one.person),
    ).toEqual(["u_a", "u_b", "u_c"]);
    const clamped = peoplePage(lines, { ...EVERYBODY, page: 9 });
    expect(clamped.page).toBe(1);
    expect(clamped.rows).toHaveLength(3);
    expect(clamped.hasNext).toBe(false);
    expect(peoplePage([], EVERYBODY)).toEqual({
      rows: [],
      page: 1,
      hasPrevious: false,
      hasNext: false,
    });
  });

  test("a body that is not a usage screen is read as nothing rather than as an empty screen", () => {
    // What breaks if this is deleted: a malformed payload is drawn as tables of nothing, which
    // tells a reader nobody asked anything.
    expect(readUsage("not a screen")).toBeNull();
    expect(readUsage(usageBody({ departments: "support" }))).toBeNull();
    expect(readUsage(usageBody({ questions: "4" }))).toBeNull();
    expect(readUsage(usageBody({ not_measured: null }))).toBeNull();
    expect(readUsage(usageBody({ tokens: undefined }))).toBeNull();
    expect(readUsage(usageBody({ tokens: null }))).toBeNull();
    expect(readUsage(usageBody({ tokens: [breakdown("person", ["a", "b"], { lines: null })] }))).toBeNull();
    expect(readUsage(usageBody({ tokens: [] }))).not.toBeNull();
    expect(readUsage(usageBody())).not.toBeNull();
  });
});

// --- Questions and gaps ------------------------------------------------------------------------

describe("the Questions and gaps screen", () => {
  test("every field the API sends is read", () => {
    // What breaks if this is deleted: a field added to the questions response arrives and is
    // dropped, which on this screen is a sentence about what cannot be listed that nobody sees.
    expect(backendModelFields(ROUTES, "QuestionsView").sort()).toEqual(
      [
        "nothing_connected",
        "answered_when_nothing_connected",
        "answered_when_nothing_found",
        "unanswered_are_recorded",
      ].sort(),
    );
    expect(readQuestions("not a screen")).toBeNull();
    expect(readQuestions(questionsBody({ nothing_connected: "yes" }))).toBeNull();
  });

  test("nothing connected is the design's no source row, quoting what askers are told, with the fix", async () => {
    // What breaks if this is deleted: every question on the install is answered with nothing
    // connected and the administrator's screen for gaps does not say so.
    const container = await mount("/questions", answering(QUESTIONS_API_PATH, questionsBody()));

    expect(container.querySelector("h2")?.textContent).toBe(UNANSWERED_HEADING);
    expect(cells(container, "Why questions could not be answered")).toEqual([
      [NO_SOURCE, sentinel("nothing-connected"), CONNECT_A_SOURCE],
    ]);
    const fix = [...container.querySelectorAll("a")].find(
      (one) => one.textContent === CONNECT_A_SOURCE,
    );
    expect(fix?.getAttribute("href")).toBe("/connectors");
  });

  test("the design's question shape and asked columns are not drawn, and the page says why", async () => {
    // What breaks if this is deleted: columns drawn blank on every row, which read as every question
    // having been answered, or the sentence saying why they are absent disappears.
    const container = await mount("/questions", answering(QUESTIONS_API_PATH, questionsBody()));
    const headers = [...container.querySelectorAll("th[scope=col]")].map((one) => one.textContent);

    expect(headers).toEqual(["Why it failed", "What every asker is told", "Fix"]);
    expect(text(container)).toContain(UNANSWERED_ARE_NOT_RECORDED);
    expect(text(container)).toContain(WORDS_ARE_NOT_KEPT);
    expect(text(container)).toContain(EXPORT_NOT_OFFERED);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  test("the not-found sentence is quoted as never counted, in the API's words", async () => {
    // What breaks if this is deleted: the page quotes a copy of the sentence that drifted, or draws
    // a no knowledge row, which counts refusals as holes in the knowledge base.
    const container = await mount("/questions", answering(QUESTIONS_API_PATH, questionsBody()));

    expect(text(container)).toContain(notFoundIsNotAGap(sentinel("nothing-found")));
    expect(cells(container, "Why questions could not be answered")).toHaveLength(1);
  });

  test("no gap is one sentence, and a withheld answer renders exactly as a connected install", async () => {
    // What breaks if this is deleted: a reader who may not be told reads something that separates
    // them from a reader on a connected install, or a helpful field upstream reaches the page.
    const connected = await mount(
      "/questions",
      answering(QUESTIONS_API_PATH, questionsBody({ nothing_connected: false })),
    );
    const leaky = await mount(
      "/questions",
      answering(
        QUESTIONS_API_PATH,
        questionsBody({ nothing_connected: false, withheld: true, reason: sentinel("grant") }),
      ),
    );

    expect(text(connected)).toContain(NO_GAP);
    expect(connected.querySelector("table")).toBeNull();
    expect(page(leaky).innerHTML).toBe(page(connected).innerHTML);
  });

  test("the sentence saying nothing records an unanswered question follows the response", async () => {
    // What breaks if this is deleted: the day a ledger records one, the page goes on saying none
    // does, because the sentence was the page's rather than the API's.
    const container = await mount(
      "/questions",
      answering(QUESTIONS_API_PATH, questionsBody({ unanswered_are_recorded: true })),
    );

    expect(text(container)).not.toContain(UNANSWERED_ARE_NOT_RECORDED);
  });
});

// --- Quality and canaries ----------------------------------------------------------------------

describe("the Quality and canaries screen", () => {
  test("every field the API sends is read", () => {
    // What breaks if this is deleted: a field added to the quality response arrives and is dropped.
    expect(backendModelFields(ROUTES, "QualityView").sort()).toEqual(
      [
        "last_canary_run",
        "canaries_started",
        "canary_interval_seconds",
        "findings_are_recorded",
        "evaluation_runs_are_recorded",
      ].sort(),
    );
    expect(backendModelFields(ROUTES, "CanaryRunView")).toEqual([
      "started_at",
      "finished_at",
      "state",
    ]);
    expect(readQuality("not a screen")).toBeNull();
    expect(readQuality(qualityBody({ canaries_started: "no" }))).toBeNull();
    expect(readQuality({ ...qualityBody(), last_canary_run: undefined })).toBeNull();
  });

  test("a finished run is drawn as finished and never as passed or green", async () => {
    // What breaks if this is deleted: a run that returned is drawn as a pass, on the screen read
    // before deciding not to worry, when nothing recorded what it found.
    const container = await mount("/quality", answering(QUALITY_API_PATH, qualityBody()));

    expect(container.querySelector("h2")?.textContent).toBe(CANARIES_HEADING);
    expect(field(container, "Last run")).toBe(
      "Started 2019-03-05T06:00:00Z, finished at 2019-03-05T06:02:00Z.",
    );
    expect(field(container, "What it found")).toBe(FINDINGS_ARE_NOT_RECORDED);
    expect(field(container, "Last run")).not.toMatch(/pass|green/i);
    expect(text(container).replace(FINDINGS_ARE_NOT_RECORDED, "")).not.toMatch(/pass|green/i);
  });

  test.each([
    ["failed", "Started 2019-03-05T06:00:00Z, failed at 2019-03-05T06:02:00Z."],
    [
      "declined",
      "Started 2019-03-05T06:00:00Z, reached in report-only mode and did not act at 2019-03-05T06:02:00Z.",
    ],
  ])("a %s run is said in its own words", (state, line) => {
    // What breaks if this is deleted: two endings drawn alike, and a run that raised reads as one
    // that returned.
    expect(
      runLine({ started_at: "2019-03-05T06:00:00Z", finished_at: "2019-03-05T06:02:00Z", state }),
    ).toBe(line);
  });

  test("an unfinished run has no finish, and says so", () => {
    // What breaks if this is deleted: a run that never returned is drawn with a finish it does not
    // have, and a canary run that hangs every time looks like one that runs.
    expect(
      runLine({ started_at: "2019-03-05T06:00:00Z", finished_at: null, state: "unfinished" }),
    ).toBe("Started 2019-03-05T06:00:00Z, started and has not finished.");
  });

  test("no run is one sentence, and a withheld run renders exactly as an install with none", async () => {
    // What breaks if this is deleted: a reader who may not see a run reads something that separates
    // them from an install where the canaries never ran, which says a run happened.
    const none = await mount(
      "/quality",
      answering(QUALITY_API_PATH, qualityBody({ last_canary_run: null })),
    );
    const leaky = await mount(
      "/quality",
      answering(
        QUALITY_API_PATH,
        qualityBody({ last_canary_run: null, withheld: true, subject: sentinel("client.cost") }),
      ),
    );

    expect(text(none)).toContain(NO_RUN);
    expect(page(leaky).innerHTML).toBe(page(none).innerHTML);
    expect(text(leaky)).not.toContain(sentinel("client.cost"));
  });

  test("whether anything starts the canaries is said, with the cadence they keep", async () => {
    // What breaks if this is deleted: the page says the canaries run every twelve hours on an
    // install where nothing starts them, or stops giving the cadence once something does.
    const idle = await mount("/quality", answering(QUALITY_API_PATH, qualityBody()));
    expect(text(idle)).toContain(notStarted(43200));

    const started = await mount(
      "/quality",
      answering(QUALITY_API_PATH, qualityBody({ canaries_started: true })),
    );
    expect(text(started)).toContain(cadence(43200));
    expect(text(started)).not.toContain(notStarted(43200));
    expect(cadence(43200)).toBe("every 12 hours");
    expect(cadence(3600)).toBe("every hour");
    expect(cadence(90)).toBe("every 90 seconds");
  });

  test("the design's rows an install cannot fill are sentences, with no figure and no control", async () => {
    // What breaks if this is deleted: synthetic users and assertions drawn as numbers nothing on an
    // install measured, or a golden score and a regression drawn empty, which read as zero.
    const container = await mount("/quality", answering(QUALITY_API_PATH, qualityBody()));

    expect(text(container)).toContain(NOT_ON_AN_INSTALL);
    expect(text(container)).toContain(NOTHING_ACTS_ON_A_RESULT);
    expect(text(container)).toContain(GOLDEN_NOT_ON_AN_INSTALL);
    expect(text(container)).toContain(NO_EVALUATION_RUN);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });
});
