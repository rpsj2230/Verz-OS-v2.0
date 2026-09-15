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

/** Every registered route pattern, and what to mount for it. */
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
    answers: { "/api/v1/agents": { items: [{ agent_id: "quote-helper", display_name: UNBROKEN }] } },
  },
  "/agents/:agentId": {
    address: "/agents/quote-helper",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/agents/quote-helper/workspace": WORKSPACE },
  },
  "/agents/:agentId/:tab": {
    address: "/agents/quote-helper/settings",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/agents/quote-helper/workspace": WORKSPACE },
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
