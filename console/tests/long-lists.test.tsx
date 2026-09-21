/**
 * Which long lists page, search, filter and sort, which offer a bulk action, and why each one that
 * does not, does not.
 *
 * `docs/admin-console.md`: "Long lists page, search, filter and sort, and bulk actions exist where
 * they are safe." This test is a measurement with a gate on it rather than a rule every page passes,
 * and it says so. On 2026-09-17 twenty addresses drew a list that the API itself says can be longer
 * than one answer and only Audit paged. `brain.listing` then gave every list route one convention,
 * a cursor, a search, a filter and an order over the rows the reader may see, and the pages were
 * rebuilt on `components/useListing.ts`; the table below is what is still excused and why.
 *
 * **What counts as a long list is read from the API, not chosen.** An address is on the list when a
 * response it draws declares `truncated` or `next_cursor` in the API's own document: the route is
 * telling its reader the list can be cut off. A list answered whole, such as the features an install
 * declares or its scheduled jobs, is bounded by the product and is not held here.
 *
 * **What counts as offering each one is read from the page and from the route together, not
 * claimed.** Each page is opened with its usual answers, told there is more, and read for controls,
 * and a control counts only over a route that takes the parameter it needs. A button asking for the
 * next page counts over a route that takes a `cursor`; a search box over one that takes `q`, or a
 * column's filter box over one that takes `filter`; a choice of order over one that takes `sort` or
 * `order`; a narrowing choice over one that takes a narrowing parameter of any name. So a control
 * that narrows or orders the rows already in the browser is not counted, which is the rule
 * `components/DataTable.tsx` argues: a page, a filter or an order computed over one answer reads as a
 * statement about everything the reader may see and is one about what arrived. A bulk action is a
 * box on each row. A capability the page offers may not also be excused, and one it does not offer
 * must be, so the table cannot say a page pages when it does not, and cannot go on excusing one after
 * it starts to.
 *
 * **A filter offers only values the reader was shown, and that is measured too.** Every option of
 * every narrowing choice on a long list must be a value somewhere in the answers the page was given,
 * except the closed vocabularies a page owns, such as a period, which are listed with their reason.
 *
 * Task ids: M27.8.6
 */

import { beforeAll, describe, expect, test } from "vitest";
import { apiDocument, declaredResponseSchema } from "./support/openapi";
import { PAGES } from "./support/pageCases";
import { mountIn } from "./support/screenStates";

type Capability = "page" | "search" | "filter" | "sort" | "bulk";
const CAPABILITIES: readonly Capability[] = ["page", "search", "filter", "sort", "bulk"];

const ROW_PLANE_HAS_NO_POSITION =
  "Records come through the row plane, the typed tool a model also calls, and brain.core.scope.Op " +
  "has no ordered comparison, so a keyset position cannot be a predicate the query compiler " +
  "accepts; an offset would re-read under the permission predicate, which brain.api refuses. The " +
  "route says whether its page was cut off, and a cursor there is a change to the model's tool.";
const ROW_PLANE_HAS_NO_ORDER =
  "The row plane orders nothing a caller chooses, for the same reason it has no position: an order " +
  "by a column a reader may not see would sort by a withheld value. Ordering one answer in the " +
  "browser orders what arrived rather than what exists.";
const EVERY_COLUMN_HAS_A_FILTER_BOX =
  "Every column the route filters already has a filter box sending an equality the route matches. " +
  "A second control per column listing the values on the page would offer the same filter twice.";
const READ_ONLY =
  "Nothing on this list is written from the console, so there is no act to do to many rows at once.";
const CHAIN_IN_ORDER =
  "A routing chain is drawn in tier and position order because that order is the chain, which " +
  "brain.routing_routes.A_CHAIN_HAS_ONE_ORDER declares: any other order would draw a fallback " +
  "above the rung it falls back from, so the route takes that one order and no other.";
const A_RUNG_IS_SAVED_ONE_AT_A_TIME =
  "Saving a rung changes the chain the next model call walks, and switching several off at once can " +
  "leave a tier with no rung switched on, which nothing refuses: " +
  "brain.routing_routes.A_RUNG_IS_SAVED_ONE_AT_A_TIME.";
const AN_APPROVAL_IS_DECIDED_FROM_ITS_OWN_CARD =
  "An approval lets one suspended action run and its card is the statement of what it will do, so " +
  "approving several at once approves artefacts nobody read, and a rejection names its own reason: " +
  "brain.approval_routes.AN_APPROVAL_IS_DECIDED_FROM_ITS_OWN_CARD.";
const AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON =
  "Approving an elevation widens one person's reach for hours on the strength of the explanation " +
  "they wrote, so approving several at once approves explanations nobody read: " +
  "brain.govern_people_routes.AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON.";
const A_GRANT_IS_REMOVED_BY_REVIEW_IN_BULK =
  "Removing several grants is the Access review screen's act, which records a decision per grant, " +
  "runs each through certify and offers it for many rows at once. People removes one capability " +
  "from one person as a correction, and a second bulk removal would be a second route to the same " +
  "write with no decision recorded.";
const AN_UNLINK_LOCKS_A_PERSON_OUT =
  "Unlinking refuses every future request a person makes, and the last administrator's link is " +
  "refused with a sentence to act on. Several unlinks at once is how a mis-ticked row locks a " +
  "colleague out of the system, so each link is retired from its own row and confirmation.";
const A_ROW_IS_A_DEPARTMENT_AND_A_PLACEMENT_NAMES_A_PERSON =
  "The rows of this list are departments. Placing somebody names a department, a team and a person, " +
  "and appointing a lead names one person for one department, so there is no act that applies to " +
  "several departments at once.";
const A_LOG_ROW_IS_READ_AND_NEVER_WRITTEN =
  "The log is read from the console and never changed from it: a kept row is removed by the " +
  "retention sweep and by nothing a person presses, so there is no act to do to many rows at once.";
/**
 * The overview screens that borrow a long list for a card, and the screen each card links to,
 * which must itself page, search and filter the same route.
 */
const OVERVIEW_CARDS: Readonly<Record<string, string>> = {
  "/department": "/agents",
  "/models": "/routing",
};
const AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST =
  "This screen is an overview, and the list it borrows is one card on it with a link to the screen " +
  "that pages, searches, filters and orders the same route; drawing a second set of controls on the " +
  "card would be a second list of the same rows.";
const A_SKILL_IS_DECIDED_FROM_ITS_OWN_BYTES =
  "The skills listed are what agents run, and nothing about a listed skill is written from it. The " +
  "writes on this screen are a review, which approves exactly the bytes of one package after " +
  "reading its body, and an assignment of one approved skill to one agent.";

/** What each long list does not offer, and why. Everything it does offer is read off the page. */
const MISSING: Readonly<Record<string, Partial<Record<Capability, string>>>> = {
  "/records/:entity": {
    page: ROW_PLANE_HAS_NO_POSITION,
    filter: EVERY_COLUMN_HAS_A_FILTER_BOX,
    sort: ROW_PLANE_HAS_NO_ORDER,
    bulk: READ_ONLY,
  },
  "/routing": { sort: CHAIN_IN_ORDER, bulk: A_RUNG_IS_SAVED_ONE_AT_A_TIME },
  "/routing/:rungId": { sort: CHAIN_IN_ORDER, bulk: A_RUNG_IS_SAVED_ONE_AT_A_TIME },
  "/models": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: CHAIN_IN_ORDER,
    bulk: READ_ONLY,
  },
  "/department": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: READ_ONLY,
  },
  "/logs": { bulk: A_LOG_ROW_IS_READ_AND_NEVER_WRITTEN },
  "/agents": { bulk: READ_ONLY },
  "/agent-templates": { bulk: READ_ONLY },
  "/approvals": { bulk: AN_APPROVAL_IS_DECIDED_FROM_ITS_OWN_CARD },
  "/adoption": { bulk: READ_ONLY },
  "/people": { bulk: A_GRANT_IS_REMOVED_BY_REVIEW_IN_BULK },
  "/people/:subject": { bulk: A_GRANT_IS_REMOVED_BY_REVIEW_IN_BULK },
  "/scopes": { bulk: READ_ONLY },
  "/skills": { bulk: A_SKILL_IS_DECIDED_FROM_ITS_OWN_BYTES },
  "/skills/:name": { bulk: A_SKILL_IS_DECIDED_FROM_ITS_OWN_BYTES },
  "/library": { bulk: READ_ONLY },
  "/sessions": {},
  "/sign-in-links": { bulk: AN_UNLINK_LOCKS_A_PERSON_OUT },
  "/audit": { bulk: READ_ONLY },
  "/departments": { bulk: A_ROW_IS_A_DEPARTMENT_AND_A_PLACEMENT_NAMES_A_PERSON },
  "/elevation": { bulk: AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON },
  "/access_review": {},
};

/**
 * The narrowing choices whose options are a closed vocabulary the page owns rather than values from
 * rows, by page and label, and why offering them names nothing about what exists.
 */
const CLOSED_VOCABULARIES: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  "/audit": {
    When:
      "The periods are the console's own four windows, the same in every install, and a window " +
      "with nothing in it is the same answer as a window the reader may see nothing in.",
  },
  "/logs": {
    Level:
      "The levels are the product's own four, the same in every install, and a level with no row " +
      "kept at it is the same answer for every reader of the log.",
    When:
      "The periods are the console's own windows over the route's start and end, the same in every " +
      "install, and the log is not narrowed per reader, so a window names nothing about what exists.",
  },
  "/adoption": {
    Period:
      "The periods are the console's own windows over the route's days parameter, the same in " +
      "every install, and a line for a department is drawn for every window alike.",
  },
};

/** The document path a request path was asked of, or null when no route matches it. */
function routeOf(path: string): string | null {
  for (const route of Object.keys(apiDocument()["paths"] as Record<string, unknown>)) {
    if (new RegExp(`^${route.replace(/\{[^}]+\}/g, "[^/]+")}$`).test(path)) {
      return route;
    }
  }
  return null;
}

/** Whether a response the route declares can be cut off. */
function bounded(path: string): boolean {
  const route = routeOf(path);
  if (route === null) {
    throw new Error(`No route in the API document answers ${path}.`);
  }
  const properties = Object.keys((declaredResponseSchema(route, "get")["properties"] ?? {}) as Record<string, unknown>);
  return properties.includes("truncated") || properties.includes("next_cursor");
}

/** Every page case drawing a list the API says can be longer than one answer. */
function longLists(): string[] {
  return Object.entries(PAGES)
    .filter(([, page]) => Object.keys(page.answers).some(bounded))
    .map(([pattern]) => pattern)
    .sort();
}

/** The page's answers, each told there is more wherever it can say so. */
function withMore(answers: Readonly<Record<string, unknown>>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(answers).map(([path, body]) => {
      if (body === null || typeof body !== "object" || Array.isArray(body) || !bounded(path)) {
        return [path, body];
      }
      const told: Record<string, unknown> = { ...(body as Record<string, unknown>) };
      if ("next_cursor" in told) {
        told["next_cursor"] = "CURSOR-SENTINEL";
      }
      if ("truncated" in told) {
        told["truncated"] = true;
      }
      return [path, told];
    }),
  );
}

function labelOf(control: HTMLSelectElement): string {
  return (control.labels?.[0]?.firstChild?.textContent ?? control.getAttribute("aria-label") ?? "").trim();
}

/** The query parameters a route declares for GET. */
function parametersOf(path: string): string[] {
  const route = routeOf(path);
  const parameters =
    (apiDocument()["paths"] as Record<string, Record<string, { parameters?: { name: string; in: string }[] }>>)[route ?? ""]?.[
      "get"
    ]?.parameters ?? [];
  return parameters.filter((one) => one.in === "query").map((one) => one.name);
}

/**
 * The parameters a search box sends: `brain.listing`'s `q`, and the log route's `event`, which is a
 * literal search within the one text a kept log row is filtered by.
 */
const SEARCH_PARAMETERS = ["q", "event"];

/** The parameters that page, search or order rather than narrow. */
const NOT_NARROWING = new Set(["limit", "cursor", "sort", "order", ...SEARCH_PARAMETERS]);

function takes(paths: readonly string[], ...names: string[]): boolean {
  return paths.some((path) => parametersOf(path).some((name) => names.includes(name)));
}

function narrowingSelects(root: Element): HTMLSelectElement[] {
  // A narrowing choice sits in a form or a group with nothing to submit: a select beside a submit
  // button is part of a write, such as an approval's reason for rejecting.
  return [...root.querySelectorAll("select")].filter((one) => {
    const holder = one.closest("form, .form, .approval-card, .card");
    return (
      !/^(Order|Sort)\b/.test(labelOf(one)) &&
      holder !== null &&
      holder.querySelector('button[type="submit"]') === null &&
      holder.closest(".approval-card") === null &&
      holder.closest(".confirm") === null
    );
  });
}

/**
 * What a mounted page offers, read from its controls and from the routes it asked.
 *
 * A pager counts only over a route that takes a cursor. The records route takes one for the one page
 * shape and refuses every value, since `brain.api_routes.RecordPage` never issues one, so its grid
 * draws no pager and the row plane's excuse still stands.
 */
function offered(root: Element, paths: readonly string[]): Set<Capability> {
  const found = new Set<Capability>();
  const buttons = [...root.querySelectorAll("button")].map((one) => (one.textContent ?? "").trim());
  if (
    takes(paths, "cursor") &&
    buttons.some((text) => ["Next", "Show older entries", "Show newer entries", "Show more"].includes(text))
  ) {
    found.add("page");
  }
  if (
    (root.querySelector('input[type="search"]') !== null && takes(paths, ...SEARCH_PARAMETERS)) ||
    (root.querySelector('input[aria-label^="Filter by "]') !== null && takes(paths, "filter"))
  ) {
    found.add("search");
  }
  const selects = [...root.querySelectorAll("select")];
  if (
    (selects.some((one) => /^(Order|Sort)\b/.test(labelOf(one))) || root.querySelector("th[aria-sort]") !== null) &&
    takes(paths, "sort", "order")
  ) {
    found.add("sort");
  }
  if (
    narrowingSelects(root).length > 0 &&
    paths.some((path) => parametersOf(path).some((name) => !NOT_NARROWING.has(name)))
  ) {
    found.add("filter");
  }
  if (root.querySelector('tbody input[type="checkbox"], .roster input[type="checkbox"]') !== null) {
    found.add("bulk");
  }
  return found;
}

beforeAll(async () => {
  await import("../src/pages/Records");
  await import("../src/pages/Matrix");
  await import("../src/pages/Approvals");
  await import("../src/pages/People");
}, 120_000);

describe("long lists", () => {
  test("every list the API says can be cut off is measured here, and nothing else is", () => {
    // What breaks if this is deleted: a new screen over a bounded route that nobody measured, because
    // the table below is typed. The set is read from the API document both ways.
    expect(Object.keys(MISSING).sort()).toEqual(longLists());
    for (const [pattern, missing] of Object.entries(MISSING)) {
      for (const [capability, reason] of Object.entries(missing)) {
        expect(reason.split(" ").length, `${pattern} ${capability} is excused without a reason`).toBeGreaterThan(10);
      }
    }
  }, 30_000);

  test("only the row plane and an overview card are excused paging, and only a fact is excused an order", () => {
    // What breaks if this is deleted: the table quietly regrowing the excuses M27.8.6 removed. Every
    // list but the records route pages, searches and filters, except a card on an overview whose
    // link goes to a screen that does all three over the same route; and the only lists not ordered
    // by the reader are the ones whose order is a fact rather than a preference.
    for (const [pattern, missing] of Object.entries(MISSING)) {
      const overview = OVERVIEW_CARDS[pattern];
      if (overview !== undefined) {
        const linked = MISSING[overview] ?? {};
        expect(["page", "search", "filter"].filter((one) => one in linked), `${overview} behind ${pattern}`).toEqual([]);
        for (const capability of ["page", "search", "filter"] as const) {
          expect(missing[capability], `${pattern} ${capability}`).toBe(AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST);
        }
        continue;
      }
      if (pattern !== "/records/:entity") {
        expect(["page", "search", "filter"].filter((one) => one in missing), pattern).toEqual([]);
      }
      if ("sort" in missing) {
        expect([ROW_PLANE_HAS_NO_ORDER, CHAIN_IN_ORDER]).toContain(missing.sort);
      }
    }
  });

  test.each(longLists())("%s offers what the table says it offers, and is excused for the rest", async (pattern) => {
    // What breaks if this is deleted: the table claiming a page pages when it does not, or going on
    // excusing a capability after the page has gained it, which is how a measurement goes stale.
    const page = PAGES[pattern];
    if (page === undefined) {
      throw new Error(`${pattern} has no page case.`);
    }
    const mounted = await mountIn(pattern, page.address, { kind: "answered", answers: withMore(page.answers) });
    const has = offered(mounted.root, Object.keys(page.answers));
    const excused = MISSING[pattern] ?? {};
    for (const capability of CAPABILITIES) {
      expect(
        has.has(capability) !== (capability in excused),
        `${pattern} ${capability}: ${has.has(capability) ? "offered and excused" : "neither offered nor excused"}`,
      ).toBe(true);
    }
  }, 30_000);

  test.each(longLists())("%s offers a filter value only when an answer carried it", async (pattern) => {
    // What breaks if this is deleted: a dropdown built from anywhere but the rows drawn, which names
    // departments, people or states the reader was never shown a row for. The answers are the whole
    // of what the page was told, so an option that is not in them was assembled by the page.
    const page = PAGES[pattern];
    if (page === undefined) {
      throw new Error(`${pattern} has no page case.`);
    }
    const mounted = await mountIn(pattern, page.address, { kind: "answered", answers: page.answers });
    const told = JSON.stringify(page.answers);
    const closed = CLOSED_VOCABULARIES[pattern] ?? {};
    for (const select of narrowingSelects(mounted.root)) {
      if (labelOf(select) in closed) {
        continue;
      }
      for (const option of [...select.querySelectorAll("option")]) {
        if (option.value === "") {
          continue;
        }
        expect(told, `${pattern} ${labelOf(select)} offers ${option.value}`).toContain(JSON.stringify(option.value).slice(1, -1));
      }
    }
  }, 30_000);
});
