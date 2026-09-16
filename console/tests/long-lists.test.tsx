/**
 * Which long lists page, search, filter and sort, which offer a bulk action, and why each one that
 * does not, does not.
 *
 * `docs/admin-console.md`: "Long lists page, search, filter and sort, and bulk actions exist where
 * they are safe." This test is a measurement with a gate on it rather than a rule every page passes,
 * and it says so. On 2026-09-17 twenty addresses drew a list that the API itself says can be longer
 * than one answer, and between them they offered what the table below records. Most of what is
 * missing is missing from the route before it is missing from the page, and the reasons say that.
 *
 * **What counts as a long list is read from the API, not chosen.** An address is on the list when a
 * response it draws declares `truncated` or `next_cursor` in the API's own document: the route is
 * telling its reader the list can be cut off. A list answered whole, such as the features an install
 * declares or its scheduled jobs, is bounded by the product and is not held here.
 *
 * **What counts as offering each one is read from the page, not claimed.** Each page is opened with
 * its usual answers, told there is more, and read for controls: a button that asks for the next page,
 * a box to type into that narrows the rows, a choice that narrows them, a choice of order or a sortable
 * column heading, and a box on each row with an act for the ones ticked. A capability the page offers
 * may not also be excused, and one it does not offer must be, so the table cannot say a page pages
 * when it does not, and cannot go on excusing one after it starts to.
 *
 * **Why so much is excused rather than built.** Most routes here take a `limit` and nothing else.
 * `components/DataTable.tsx` argues why a page, a filter or an order computed in a browser over one
 * bounded, permission-filtered answer is worse than none: it reads as a statement about everything
 * the reader may see and is a statement about what happened to arrive. The screens that do narrow in
 * the browser say so on the screen, under `governPeopleQuery.A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`.
 * Paging, search and order for the rest are route changes first, and M27.8.6 stays open until they
 * are made.
 *
 * Task ids: M27.8.6
 */

import { beforeAll, describe, expect, test } from "vitest";
import { apiDocument, declaredResponseSchema } from "./support/openapi";
import { PAGES } from "./support/pageCases";
import { mountIn } from "./support/screenStates";

type Capability = "page" | "search" | "filter" | "sort" | "bulk";
const CAPABILITIES: readonly Capability[] = ["page", "search", "filter", "sort", "bulk"];

const NO_CURSOR =
  "The route answers one page of at most its limit and says only whether it was cut off. It takes " +
  "no cursor, so there is no second page to ask for, and a second page cut from the rows already " +
  "received would be a page of what arrived rather than of what exists.";
const NO_NARROWING =
  "The route takes no search and no filter, and this page draws none over the rows it was given, " +
  "because narrowing one bounded answer in the browser reads as a search of everything the reader " +
  "may see.";
const NO_ORDER =
  "The rows arrive in the order the route chose and the route takes no order. Sorting one bounded " +
  "answer in the browser orders what arrived rather than what exists.";
const READ_ONLY =
  "Nothing on this list is written from the console, so there is no act to do to many rows at once.";
const ONE_ROW_AT_A_TIME =
  "Each write on this list is one confirmed act on one row that can be refused on its own, and no " +
  "route takes a set of rows. A bulk action would be a loop of writes whose partial failure the page " +
  "has no way to state, so it is not safe until a route takes the set.";
const TEXT_FILTER_ONLY =
  "Each column's filter is text the route matches, sent from the grid's own filter boxes. The route " +
  "offers no list of values to choose from, and one built from the rows on the page would offer the page.";
const NARROWED_BY_CHOICE =
  "The rows are narrowed by choosing from the values they carry rather than by typing, which is the " +
  "only narrowing over one bounded page that cannot suggest a value the reader was not shown.";
const LEDGER_FILTERS =
  "The ledger is narrowed by the route's own action, kind, actor and period, and the route takes no " +
  "free text; a search over entry details is a query on the ledger the route does not offer yet.";
const CHAIN_IN_ORDER =
  "A routing chain is drawn in tier and position order because that order is the chain; any other " +
  "order would draw a fallback before the rung it falls back from.";

/** What each long list does not offer, and why. Everything it does offer is read off the page. */
const MISSING: Readonly<Record<string, Partial<Record<Capability, string>>>> = {
  "/records/:entity": { page: NO_CURSOR, filter: TEXT_FILTER_ONLY, sort: NO_ORDER, bulk: READ_ONLY },
  "/routing": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: CHAIN_IN_ORDER, bulk: ONE_ROW_AT_A_TIME },
  "/routing/:rungId": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: CHAIN_IN_ORDER, bulk: ONE_ROW_AT_A_TIME },
  "/models": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: CHAIN_IN_ORDER, bulk: READ_ONLY },
  "/department": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/agents": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/agent-templates": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/approvals": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: ONE_ROW_AT_A_TIME },
  "/adoption": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/people": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: ONE_ROW_AT_A_TIME },
  "/people/:subject": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: ONE_ROW_AT_A_TIME },
  "/scopes": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/skills": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/skills/:name": { page: NO_CURSOR, search: NO_NARROWING, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/library": { page: NO_CURSOR, bulk: READ_ONLY },
  "/sessions": { page: NO_CURSOR, search: NARROWED_BY_CHOICE, bulk: ONE_ROW_AT_A_TIME },
  "/sign-in-links": { page: NO_CURSOR, filter: NO_NARROWING, sort: NO_ORDER, bulk: ONE_ROW_AT_A_TIME },
  "/audit": { search: LEDGER_FILTERS, bulk: READ_ONLY },
  "/departments": { page: NO_CURSOR, filter: NO_NARROWING, sort: NO_ORDER, bulk: READ_ONLY },
  "/access_review": { page: NO_CURSOR, search: NARROWED_BY_CHOICE, sort: NO_ORDER, bulk: ONE_ROW_AT_A_TIME },
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
  return (control.labels?.[0]?.textContent ?? control.getAttribute("aria-label") ?? "").trim();
}

/** Whether a route takes a cursor, which is what a second page is asked for with. */
function takesCursor(path: string): boolean {
  const route = routeOf(path);
  const parameters = (((apiDocument()["paths"] as Record<string, Record<string, { parameters?: { name: string; in: string }[] }>>)[route ?? ""]?.["get"]?.parameters) ?? []);
  return parameters.some((one) => one.in === "query" && one.name === "cursor");
}

/**
 * What a mounted page offers, read from its controls and, for paging, from the route as well.
 *
 * A pager counts only over a route that takes a cursor. The grid draws Previous and Next over every
 * answer it is given, and over a route that never sends a cursor those two buttons can never be
 * pressed: `brain.api_routes.RecordPage` says why the records route's is always null.
 */
function offered(root: Element, paths: readonly string[]): Set<Capability> {
  const found = new Set<Capability>();
  const buttons = [...root.querySelectorAll("button")].map((one) => (one.textContent ?? "").trim());
  if (
    paths.some(takesCursor) &&
    buttons.some((text) => ["Next", "Show older entries", "Show newer entries", "Show more"].includes(text))
  ) {
    found.add("page");
  }
  if (root.querySelector('input[type="search"], input[aria-label^="Filter by "]') !== null) {
    found.add("search");
  }
  const selects = [...root.querySelectorAll("select")];
  if (selects.some((one) => /^(Order|Sort)\b/.test(labelOf(one))) || root.querySelector("th[aria-sort]") !== null) {
    found.add("sort");
  }
  // A narrowing choice sits in a form or a group with nothing to submit: a select beside a submit
  // button is part of a write, such as an approval's reason for rejecting.
  if (
    selects.some((one) => {
      const holder = one.closest("form, .form, .approval-card, .card");
      return !/^(Order|Sort)\b/.test(labelOf(one)) && holder !== null && holder.querySelector('button[type="submit"]') === null && holder.closest(".approval-card") === null;
    })
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
});
