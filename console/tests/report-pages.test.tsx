/**
 * The three Report screens: that each draws what the API sent, and computes nothing.
 *
 * **Reachable means through the application's own route table.** Every test here mounts
 * `routes` from `src/App.tsx` on a memory router, signed in through the real session modules
 * and answered by a stand-in API, so a test passes only if the address resolves and the shell
 * renders the page. A test that imported the component directly would prove the component
 * works and not that anybody can open it, which is the failure `brain.ops.console_screens`
 * exists to count.
 *
 * **The property most of this file exists for is that a narrowed answer renders as an answer.**
 * A reader whose usage grant names one department is sent a reading with no lanes, and so is a
 * reader on an install that promises nothing. The two bodies are equal, and these tests hold
 * the two rendered pages to being equal as markup, because the place that rule usually breaks
 * is a helpful sentence added to an empty table.
 *
 * **Every figure is asserted to be the API's rather than the browser's.** The spend page is
 * handed a total that disagrees with its own lines, which no real response can carry because
 * `brain.console.spend_view.Report` asserts the equality in its constructor, and the page is
 * held to printing what it was sent. That is the only way to tell a printed field from a
 * recomputed one, and the recomputed one is what a console grows the first time somebody bounds
 * a page.
 *
 * **The keyboard half is here rather than in `keyboard-access.test.tsx`** because what these
 * pages add to the keyboard story is three navigation entries and three tables, and the
 * question worth asking of them is whether they added anything the keyboard cannot reach.
 *
 * Task ids: M27.7.15, M27.7.16, M27.7.17
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ADOPTION_HEADING, MORE_DEPARTMENTS, NO_ADOPTION } from "../src/pages/Adoption";
import { adoptionApiPath, readAdoptionPage } from "../src/pages/adoptionQuery";
import { NOT_BUILT_YET, SPEND_HEADING, WITHOUT_AUTOMATION } from "../src/pages/Spend";
import { spendApiPath } from "../src/pages/spendQuery";
import { NO_LANES, SERVICE_LEVELS_HEADING } from "../src/pages/ServiceLevels";
import { ratePercent, serviceLevelsApiPath } from "../src/pages/serviceLevelsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { declaredQueryParameters } from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";

const SERVICE_LEVELS_API = "/api/v1/report/service-levels";
const SPEND_API = "/api/v1/report/spend";
const ADOPTION_API = "/api/v1/report/adoption";

const SERVICE_LEVELS_ADDRESS = "/service-levels";
const SPEND_ADDRESS = "/spend";
const ADOPTION_ADDRESS = "/adoption";

interface Mounted {
  readonly container: HTMLElement;
}

/** The whole console at one address, with the stand-in API answering by path and nothing else. */
async function consoleAt(
  path: string,
  answers: Readonly<Record<string, unknown>>,
): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url) {
      const asked = new URL(url, CONSOLE_ORIGIN).pathname;
      if (!(asked in answers)) {
        return null;
      }
      return new Response(JSON.stringify(answers[asked]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('p.note[role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
}

function page(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>("article.page");
  if (!found) {
    throw new Error("No page was rendered.");
  }
  return found;
}

/** Every cell of a rendered table, row by row, as a person reads them. */
function rows(container: HTMLElement): string[][] {
  return [...page(container).querySelectorAll("tbody tr")].map((row) =>
    [...row.querySelectorAll("th, td")].map((cell) => cell.textContent ?? ""),
  );
}

function lane(name: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    lane: name,
    objective_p95_ms: 2000,
    objective_success_rate: 0.99,
    p95_ms: 1200,
    success_rate: 0.995,
    requests: 40,
    met: true,
    shortfalls: [],
    ...over,
  };
}

function reading(lanes: Record<string, unknown>[]): Record<string, unknown> {
  return { start: "2019-03-04T09:00:00Z", end: "2019-03-05T09:00:00Z", lanes };
}

function spendBody(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    dimension: "department",
    built: true,
    lines: [
      { key: "support", cost_minor: 700 },
      { key: "finance", cost_minor: 300 },
    ],
    machine_included: false,
    total_minor: 1000,
    as_of: "2019-03-04T09:00:00Z",
    freshness: "live",
    ...over,
  };
}

function adoptionBody(
  lines: Record<string, unknown>[],
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  return { items: lines, next_cursor: null, total: null, truncated: false, ...over };
}

// --------------------------------------------------------------------- service levels
describe("the service levels screen", () => {
  test("it draws the lanes the API sent, with the figures the API measured", async () => {
    // What breaks if this is deleted: every disclosure test below is satisfied by a page that
    // draws nothing at all, because an empty reading is exactly what a refused reader gets.
    const { container } = await consoleAt(SERVICE_LEVELS_ADDRESS, {
      [SERVICE_LEVELS_API]: reading([lane("fast"), lane("answer", { met: false, shortfalls: ["the answer lane returned 98.0% of requests against 99.0%"] })]),
    });

    expect(container.querySelector("h1")?.textContent).toBe(SERVICE_LEVELS_HEADING);
    expect(rows(container).map((row) => row[0])).toEqual(["fast", "answer"]);
    expect(rows(container)[0]?.[4]).toBe(ratePercent(0.995));
  });

  test("a reading with no lanes says there is nothing to show and says nothing about why", async () => {
    // What breaks if this is deleted: a sentence naming a grant, or even one saying something
    // was narrowed, appears on the empty table, and a reader can tell "you may not be told"
    // from "there is nothing to tell".
    const { container } = await consoleAt(SERVICE_LEVELS_ADDRESS, {
      [SERVICE_LEVELS_API]: reading([]),
    });

    const markup = page(container).innerHTML;
    expect(markup).toContain(NO_LANES);
    expect(markup).not.toMatch(/grant|permission|scope|narrow|department|withheld|hidden/i);
  });

  test("a field beside an empty reading reaches nothing, so a narrowing cannot be drawn", async () => {
    // What breaks if this is deleted: the day something upstream adds a flag saying a reading
    // was narrowed, a renderer that is generous with the body draws it, and the two reasons a
    // reading arrives empty become distinguishable in the browser. The bare body and the leaky
    // one must render byte for byte the same markup.
    const bare = await consoleAt(SERVICE_LEVELS_ADDRESS, {
      [SERVICE_LEVELS_API]: reading([]),
    });
    const leaky = await consoleAt(SERVICE_LEVELS_ADDRESS, {
      [SERVICE_LEVELS_API]: {
        ...reading([]),
        narrowed: true,
        hidden: 4,
        withheld_lanes: ["answer", "task"],
      },
    });

    expect(page(leaky.container).innerHTML).toBe(page(bare.container).innerHTML);
    expect(page(leaky.container).innerHTML).not.toMatch(/answer|task|4/);
  });

  test("a figure the sample could not support is drawn as nothing rather than as zero", async () => {
    // What breaks if this is deleted: a lane with too few requests for a rank shows a p95 of
    // 0 ms and a success rate of 0%, which reads as an outage rather than as a quiet lane.
    const { container } = await consoleAt(SERVICE_LEVELS_ADDRESS, {
      [SERVICE_LEVELS_API]: reading([
        lane("task", { p95_ms: null, success_rate: null, requests: 0, objective_p95_ms: null }),
      ]),
    });

    const drawn = rows(container)[0] ?? [];
    expect(drawn[2]).not.toMatch(/0/);
    expect(drawn[4]).not.toMatch(/0/);
    expect(drawn[6]).toBe("0");
  });

  test("the request this screen makes names only parameters the route declares", () => {
    // What breaks if this is deleted: a parameter is renamed on the route, the console keeps
    // sending the old one, FastAPI discards it without a word, and a person reads a window
    // they did not ask for as the one they did.
    const declared = new Set(declaredQueryParameters(`${SERVICE_LEVELS_API}`, "get"));
    const asked = [...new URL(serviceLevelsApiPath(), CONSOLE_ORIGIN).searchParams.keys()];

    expect(asked.length).toBeGreaterThan(0);
    expect(asked.filter((name) => !declared.has(name))).toEqual([]);
  });
});

// ------------------------------------------------------------------------------- spend
describe("the spend screen", () => {
  test("it draws every line the API sent, with the total the API sent beside them", async () => {
    // What breaks if this is deleted: the page draws nothing and every rule below is kept by
    // a screen that shows no figures at all.
    const { container } = await consoleAt(SPEND_ADDRESS, { [SPEND_API]: spendBody() });

    expect(container.querySelector("h1")?.textContent).toBe(SPEND_HEADING);
    expect(rows(container)).toEqual([
      ["support", "7.00"],
      ["finance", "3.00"],
    ]);
    expect(page(container).querySelector("tfoot")?.textContent).toContain("10.00");
  });

  test("the total on the page is the field the API sent and is never the sum of the rows", async () => {
    // What breaks if this is deleted: the console starts adding the rows up, and the day a
    // page is bounded the figure on screen quietly stops being the figure the API stands
    // behind. No real response can carry these two values together, which is the point: only
    // a body the API could not send can tell a printed field from a computed one.
    const { container } = await consoleAt(SPEND_ADDRESS, {
      [SPEND_API]: spendBody({ total_minor: 5500 }),
    });

    expect(page(container).querySelector("tfoot")?.textContent).toContain("55.00");
    expect(page(container).querySelector("tfoot")?.textContent).not.toContain("10.00");
  });

  test("a report nobody has built says so, and draws no zero", async () => {
    // What breaks if this is deleted: a fresh install shows every department a total of zero,
    // which is a figure and a false one, on the screen somebody reads before deciding not to
    // worry.
    const { container } = await consoleAt(SPEND_ADDRESS, {
      [SPEND_API]: spendBody({ built: false, lines: [], total_minor: null, as_of: null, freshness: "unstated" }),
    });

    const markup = page(container).innerHTML;
    expect(markup).toContain(NOT_BUILT_YET);
    expect(markup).not.toContain("0.00");
    expect(markup).not.toContain("<table");
  });

  test("the page says whether automated traffic was counted, from the answer and not the request", async () => {
    // What breaks if this is deleted: the sentence is written from what this console asked
    // for, the default changes on the route, and the page describes the old one for ever.
    const excluded = await consoleAt(SPEND_ADDRESS, { [SPEND_API]: spendBody() });
    const included = await consoleAt(SPEND_ADDRESS, {
      [SPEND_API]: spendBody({ machine_included: true }),
    });

    expect(page(excluded.container).innerHTML).toContain(WITHOUT_AUTOMATION);
    expect(page(included.container).innerHTML).not.toContain(WITHOUT_AUTOMATION);
  });

  test("a narrowed report draws its own lines and nothing about the ones it does not have", async () => {
    // What breaks if this is deleted: a residual line, a company figure or a share arrives
    // beside a filtered breakdown, which is the hidden total with a percent sign on it.
    const { container } = await consoleAt(SPEND_ADDRESS, {
      [SPEND_API]: spendBody({ lines: [{ key: "support", cost_minor: 700 }], total_minor: 700 }),
    });

    expect(rows(container)).toEqual([["support", "7.00"]]);
    expect(page(container).innerHTML).not.toMatch(/others|remaining|of total|hidden|withheld/i);
  });

  test("the request this screen makes names only parameters the route declares", () => {
    // What breaks if this is deleted: the dimension is sent under a name the route does not
    // declare, FastAPI discards it, and the page is headed department while showing models.
    const declared = new Set(declaredQueryParameters(SPEND_API, "get"));
    const asked = [...new URL(spendApiPath(), CONSOLE_ORIGIN).searchParams.keys()];

    expect(asked.length).toBeGreaterThan(0);
    expect(declared.size).toBeGreaterThan(0);
    expect(asked.filter((name) => !declared.has(name))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------- adoption
describe("the adoption screen", () => {
  test("it draws a line for every department the API sent, including one that asked nothing", async () => {
    // What breaks if this is deleted: the zero rows are tidied away, the departments left on
    // the page are exactly the ones with traffic, and a reader learns which of the
    // departments they may see has stopped using the system.
    const { container } = await consoleAt(ADOPTION_ADDRESS, {
      [ADOPTION_API]: adoptionBody([
        { department: "finance", questions: 0, people: 0 },
        { department: "support", questions: 12, people: 3 },
      ]),
    });

    expect(container.querySelector("h1")?.textContent).toBe(ADOPTION_HEADING);
    expect(rows(container)).toEqual([
      ["finance", "0", "0"],
      ["support", "12", "3"],
    ]);
  });

  test("a page with no lines says there is nothing to show and names no reason", async () => {
    // What breaks if this is deleted: the page explains an empty answer, and a reader holding
    // no usage grant is told that a report exists which they may not see.
    const { container } = await consoleAt(ADOPTION_ADDRESS, {
      [ADOPTION_API]: adoptionBody([]),
    });

    const markup = page(container).innerHTML;
    expect(markup).toContain(NO_ADOPTION);
    expect(markup).not.toMatch(/grant|permission|scope|withheld|hidden/i);
  });

  test("a full page says there is more and puts no number in the sentence", async () => {
    // What breaks if this is deleted: a count arrives beside a bounded listing and the reader
    // learns the size of a set they were shown part of.
    const { container } = await consoleAt(ADOPTION_ADDRESS, {
      [ADOPTION_API]: adoptionBody([{ department: "support", questions: 1, people: 1 }], {
        truncated: true,
        total: 47,
      }),
    });

    expect(page(container).innerHTML).toContain(MORE_DEPARTMENTS);
    expect(MORE_DEPARTMENTS).not.toMatch(/[0-9]/);
    expect(page(container).innerHTML).not.toContain("47");
  });

  test("a total the API sends reaches nothing on the page, because the page has no field for one", () => {
    // What breaks if this is deleted: `total` acquires a home in the console's own answer,
    // which is one line away from being rendered.
    const held = readAdoptionPage(
      adoptionBody([{ department: "support", questions: 1, people: 1 }], { total: 47, hidden: 3 }),
    );

    expect(Object.keys(held).sort()).toEqual(["lines", "truncated"]);
  });

  test("the request this screen makes names only parameters the route declares", () => {
    // What breaks if this is deleted: the window or the bound is sent under a name the route
    // does not declare, and the page silently shows the route's default instead.
    const declared = new Set(declaredQueryParameters(ADOPTION_API, "get"));
    const asked = [...new URL(adoptionApiPath(), CONSOLE_ORIGIN).searchParams.keys()];

    expect(asked.length).toBeGreaterThan(0);
    expect(declared.size).toBeGreaterThan(0);
    expect(asked.filter((name) => !declared.has(name))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------- keyboard
describe("getting round the report screens without a mouse", () => {
  test("each screen is reachable from the navigation as a link the tab key stops on", async () => {
    // What breaks if this is deleted: a section is added to the shell as something that is not
    // an anchor, and a person on a keyboard cannot reach the screen at all. These three are on the
    // company console's menu, so the stand-in API gives that console.
    const { container } = await consoleAt(SERVICE_LEVELS_ADDRESS, {
      [SERVICE_LEVELS_API]: reading([]),
      [NAVIGATION_ADDRESS]: COMPANY_CONSOLE,
    });
    const addresses = [...container.querySelectorAll("nav.shell__nav a")].map((link) =>
      link.getAttribute("href"),
    );

    expect(addresses).toContain(SERVICE_LEVELS_ADDRESS);
    expect(addresses).toContain(SPEND_ADDRESS);
    expect(addresses).toContain(ADOPTION_ADDRESS);
  });

  test("none of the three pages adds anything the keyboard cannot reach", async () => {
    // What breaks if this is deleted: a sortable header or a row that expands arrives as a div
    // with a click handler, which looks identical to a button and is reachable by nothing.
    for (const [address, answers] of [
      [SERVICE_LEVELS_ADDRESS, { [SERVICE_LEVELS_API]: reading([lane("fast")]) }],
      [SPEND_ADDRESS, { [SPEND_API]: spendBody() }],
      [
        ADOPTION_ADDRESS,
        { [ADOPTION_API]: adoptionBody([{ department: "support", questions: 1, people: 1 }]) },
      ],
    ] as const) {
      const { container } = await consoleAt(address, answers);
      const inside = page(container);

      expect(inside.querySelectorAll("[tabindex]")).toHaveLength(0);
      expect(inside.querySelectorAll("[onclick]")).toHaveLength(0);
    }
  });

  test("every table on the three screens names itself and gives each row a header", async () => {
    // What breaks if this is deleted: a grid of figures arrives with no caption and no row
    // header, and somebody reading it with a screen reader hears a column of numbers with
    // nothing saying which department they belong to.
    for (const [address, answers] of [
      [SERVICE_LEVELS_ADDRESS, { [SERVICE_LEVELS_API]: reading([lane("fast")]) }],
      [SPEND_ADDRESS, { [SPEND_API]: spendBody() }],
      [
        ADOPTION_ADDRESS,
        { [ADOPTION_API]: adoptionBody([{ department: "support", questions: 1, people: 1 }]) },
      ],
    ] as const) {
      const { container } = await consoleAt(address, answers);
      const table = page(container).querySelector("table");

      expect(table?.querySelector("caption")?.textContent ?? "").not.toBe("");
      for (const row of table?.querySelectorAll("tbody tr") ?? []) {
        expect(row.querySelector('th[scope="row"]')).not.toBeNull();
      }
      for (const header of table?.querySelectorAll("thead th") ?? []) {
        expect(header.getAttribute("scope")).toBe("col");
      }
    }
  });
});
