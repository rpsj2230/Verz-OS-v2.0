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
import { PAGES, awaited } from "./support/pageCases";
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
const DOCUMENT_PLANE_HAS_NO_POSITION =
  "A cited document comes through knowledge.read_document, the typed tool a model also calls, and " +
  "it takes a reference and a bound and no position, so there is nothing a cursor, a search or a " +
  "filter could be passed to; the route says when the document is longer than the page, and a " +
  "cursor there is a change to the model's tool, as it is for the row plane.";
const A_DOCUMENT_HAS_ONE_ORDER =
  "A document is read in the order it was written, which is the order its passages are stored in; " +
  "any other order would put a sentence before the one it follows.";
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
  "approving several at once approves requests nobody read, and a rejection names its own reason: " +
  "brain.approval_routes.AN_APPROVAL_IS_DECIDED_FROM_ITS_OWN_CARD.";
const AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON =
  "Approving an elevation widens one person's reach for hours on the strength of the explanation " +
  "they wrote, so approving several at once approves explanations nobody read: " +
  "brain.govern_people_routes.AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON.";
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
  "/": "/audit",
  "/department": "/agents",
  // The Profile and About views read the Departments row and the directory's people for one
  // department, and link to the Departments page, which pages, searches and filters that route.
  "/department/:view": "/departments",
  "/agents/:agentId/:tab": "/routing",
  // One skill's page reads the Skills page's answer narrowed to its name; the library itself is
  // paged, searched, filtered and ordered on /skills.
  "/skills/:name": "/skills",
  "/skills/:name/:view": "/skills",
  "/models/:provider": "/models",
  "/models/:provider/:view": "/models",
  "/people/:personId": "/agents",
  // A person's Access view offers the roster's first page as the agents a run can be previewed
  // through, and the Agents page pages, searches, filters and orders the same route.
  "/people/:personId/:view": "/agents",
  "/roles": "/people",
  "/departments/:slug": "/departments",
  "/departments/:slug/:view": "/scopes",
  "/audit/subject/:kind/:id/:view": "/audit/subject/:kind/:id",
  "/access_review/:kind/:rowId": "/access_review",
  "/elevation/:requestId": "/elevation",
  // New agent offers the gallery's first page as the templates a draft can start from, and links
  // to the gallery, which pages, searches and filters the same route.
  "/agents/new": "/agent-templates",
};

const ONE_HOLDING_IS_DECIDED_ON_ITS_OWN_PAGE =
  "This page is one holding, and keeping or removing it is one decision; several are kept or " +
  "removed together from the Access review list, which selects them.";
const AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST =
  "This screen is an overview, and the list it borrows is one card on it with a link to the screen " +
  "that pages, searches, filters and orders the same route; drawing a second set of controls on the " +
  "card would be a second list of the same rows.";
const A_PIN_IS_ONE_AGENTS =
  "The one write beside this list pins a model for this agent alone, and the steps drawn are the " +
  "level's, which are saved one at a time on the Routing screen, so there is no act to do to many " +
  "of them from here.";
const A_PROVIDER_PAGE_IS_ONE_PROVIDER =
  "This page is one provider, and the steps it lists are that provider's, drawn in the chain's " +
  "order and changed one at a time on the Routing screen, so there is no act to do to several here.";
const A_SKILL_IS_DECIDED_FROM_ITS_OWN_BYTES =
  "Every write on a skill is about one version or one agent: a review approves exactly the bytes a " +
  "reviewer read, a retirement names the agents still running that version for somebody to detach, " +
  "and a detachment ends one assignment, so there is no act that applies to several rows at once.";

const A_DRAFT_STARTS_FROM_ONE_TEMPLATE =
  "A draft is started from one template and is its author's own, so there is no act that starts " +
  "one from several templates at once.";
const A_DEPARTMENT_PAGE_IS_ONE_DEPARTMENT =
  "This page is one department, and its only writes rename or retire that department, each " +
  "confirmed on its own, so there is no act to do to several rows at once.";
const AN_UNBINDING_IS_ONE_PERSONS_CHAT =
  "Unbinding stops a chat account being answered as its person, at once, and is recorded against " +
  "them; it is confirmed one person at a time so nobody's chat is taken away as a side effect of " +
  "somebody else's.";

/**
 * The Models screen as the owner drew it on 2026-09-03 and restated on 2026-09-29: providers as a row
 * of cards and his failover matrix as one table, with no search box and no filter on either.
 */
const THE_OWNER_DREW_IT_WHOLE =
  "The owner's design of record for the Models screen, 2026-09-03 and restated 2026-09-29, draws the " +
  "providers as a row of cards and the failover matrix as one table with no search box and no " +
  "filter: a handful of providers and a dozen steps are read at a glance, a narrowed matrix is not " +
  "the chain any question walks, and each list still pages when the API says there is more.";
const THE_PROVIDERS_KEEP_THE_PRODUCTS_ORDER =
  "The providers are drawn in the order the route answers them, built in first and then those an " +
  "administrator added, which is the order the owner's screen reads them in; the route takes no " +
  "other order from this page.";
const A_PROVIDER_IS_SWITCHED_ONE_AT_A_TIME =
  "A provider is given a key, tested and switched from its own card, each confirmed with its own " +
  "consequence: switching several off at once can leave a level with no provider answering, which " +
  "nothing refuses, and a test spends tokens under the presser's name.";
/** The screens drawn whole by the owner's design, excused search and filter for that reason alone. */
const DRAWN_WHOLE: ReadonlySet<string> = new Set(["/models", "/routing", "/routing/:rungId"]);

const A_RUN_IS_WRITTEN_BY_THE_WORKER =
  "A job's past runs are rows the worker writes as it runs the job, and nothing a person presses " +
  "changes one: pause, resume and run now act on the job, from its own header, so there is no act " +
  "to do to many runs at once.";

/** What each long list does not offer, and why. Everything it does offer is read off the page. */
/**
 * The two lists read through a tool a model also calls, whose request has no position to page by:
 * the row plane behind Records and the document plane behind a cited document. Excused paging,
 * search and filter for that reason and no other.
 */
const THROUGH_A_MODELS_TOOL: Readonly<Record<string, string>> = {
  "/records/:entity": ROW_PLANE_HAS_NO_POSITION,
  "/ask/documents/:documentId": DOCUMENT_PLANE_HAS_NO_POSITION,
};

const MISSING: Readonly<Record<string, Partial<Record<Capability, string>>>> = {
  // A document's passages are its text in reading order, read through the handler the answer used,
  // which takes a reference and a bound and nothing to page, search, filter or order by.
  "/ask/documents/:documentId": {
    page: DOCUMENT_PLANE_HAS_NO_POSITION,
    search: DOCUMENT_PLANE_HAS_NO_POSITION,
    filter: DOCUMENT_PLANE_HAS_NO_POSITION,
    sort: A_DOCUMENT_HAS_ONE_ORDER,
    bulk: READ_ONLY,
  },
  "/records/:entity": {
    page: ROW_PLANE_HAS_NO_POSITION,
    filter: EVERY_COLUMN_HAS_A_FILTER_BOX,
    sort: ROW_PLANE_HAS_NO_ORDER,
    bulk: READ_ONLY,
  },
  "/routing": {
    search: THE_OWNER_DREW_IT_WHOLE,
    filter: THE_OWNER_DREW_IT_WHOLE,
    sort: CHAIN_IN_ORDER,
    bulk: A_RUNG_IS_SAVED_ONE_AT_A_TIME,
  },
  "/models": {
    search: THE_OWNER_DREW_IT_WHOLE,
    filter: THE_OWNER_DREW_IT_WHOLE,
    sort: THE_PROVIDERS_KEEP_THE_PRODUCTS_ORDER,
    bulk: A_PROVIDER_IS_SWITCHED_ONE_AT_A_TIME,
  },
  // A provider's page draws that provider out of the providers list and links back to it.
  "/models/:provider": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: CHAIN_IN_ORDER,
    bulk: A_PROVIDER_PAGE_IS_ONE_PROVIDER,
  },
  "/models/:provider/:view": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: CHAIN_IN_ORDER,
    bulk: A_PROVIDER_PAGE_IS_ONE_PROVIDER,
  },
  "/routing/:rungId": {
    search: THE_OWNER_DREW_IT_WHOLE,
    filter: THE_OWNER_DREW_IT_WHOLE,
    sort: CHAIN_IN_ORDER,
    bulk: A_RUNG_IS_SAVED_ONE_AT_A_TIME,
  },
  // The Profile's model card draws the agent's level from the matrix and links to the Routing screen.
  "/agents/:agentId/:tab": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: CHAIN_IN_ORDER,
    bulk: A_PIN_IS_ONE_AGENTS,
  },
  "/": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: READ_ONLY,
  },
  "/department": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: READ_ONLY,
  },
  "/department/:view": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: A_DEPARTMENT_PAGE_IS_ONE_DEPARTMENT,
  },
  "/logs": { bulk: A_LOG_ROW_IS_READ_AND_NEVER_WRITTEN },
  "/agents": {},
  "/connectors": {},
  "/automations": {},
  "/agent-templates": {},
  "/agents/new": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: A_DRAFT_STARTS_FROM_ONE_TEMPLATE,
  },
  "/jobs/:name": {},
  "/approvals": { bulk: AN_APPROVAL_IS_DECIDED_FROM_ITS_OWN_CARD },
  "/adoption": { bulk: READ_ONLY },
  "/people": {},
  // A person's page borrows the roster for the agents they steward, and links to the Agents list.
  "/people/:personId": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: READ_ONLY,
  },
  "/people/:personId/:view": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: READ_ONLY,
  },
  "/scopes": {},
  // The Roles tab reads the directory's first page only to put names to the ids the Approver flag
  // and the directory group sync carry, and each name links to the person on the People list.
  "/roles": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
  },
  "/skills": {},
  "/skills/:name": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: A_SKILL_IS_DECIDED_FROM_ITS_OWN_BYTES,
  },
  "/skills/:name/:view": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: A_SKILL_IS_DECIDED_FROM_ITS_OWN_BYTES,
  },
  "/library": {},
  "/sessions": {},
  "/sign-in-links": {},
  "/service-accounts": {},
  "/audit": {},
  "/company/activity": {},
  // One subject's page pages, searches, filters and orders the ledger narrowed to that subject.
  "/audit/subject/:kind/:id": {},
  // Its access changes view reads the ledger only for the header's newest entry.
  "/audit/subject/:kind/:id/:view": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
  },
  "/credentials": {},
  "/departments": {},
  // One department's page asks the list route for its own row, and its Scopes view the scopes naming
  // it; the lists that page, search and filter those routes are Departments and Scopes.
  "/departments/:slug": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: A_ROW_IS_A_DEPARTMENT_AND_A_PLACEMENT_NAMES_A_PERSON,
  },
  "/departments/:slug/:view": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: A_ROW_IS_A_DEPARTMENT_AND_A_PLACEMENT_NAMES_A_PERSON,
  },
  "/elevation": {},
  // One request's page asks the requests list for that row by id; Elevation requests pages it.
  "/elevation/:requestId": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON,
  },
  "/access_review": {},
  // One holding's page asks the review for that row by id; Access review pages it.
  "/access_review/:kind/:rowId": {
    page: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    search: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    filter: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    sort: AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST,
    bulk: ONE_HOLDING_IS_DECIDED_ON_ITS_OWN_PAGE,
  },
  "/access-requests": {},
  "/channels": {},
  "/channels/:name": { bulk: AN_UNBINDING_IS_ONE_PERSONS_CHAT },
};

/**
 * The narrowing choices whose options are a closed vocabulary the page owns rather than values from
 * rows, by page and label, and why offering them names nothing about what exists.
 */
const CLOSED_VOCABULARIES: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  "/library": {
    Review:
      "Due and not due are the product's own two words, the same in every install, and each row " +
      "carries one of them, so offering the other names nothing about what exists.",
  },
  "/access-requests": {
    "Where it stands":
      "Open and handled are the route's own two words, the same in every install, and each row " +
      "carries one of them, so offering the other names nothing about what exists.",
  },
  "/audit": {
    When:
      "The periods are the console's own four windows, the same in every install, and a window " +
      "with nothing in it is the same answer as a window the reader may see nothing in.",
  },
  "/audit/subject/:kind/:id": {
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
  if (route === null && awaited(path)) {
    // A route another package is building, answered by a page case in the shape it was briefed
    // with. It is read against the document the day it is declared there.
    return false;
  }
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
  // The page kit's table selects with a checkbox drawn as a button (`kit/EntityTable`), and a
  // selection is a bulk act in itself: the selected rows export, and a route that takes a set acts.
  if (root.querySelector('tbody input[type="checkbox"], .roster input[type="checkbox"], tbody [role="checkbox"]') !== null) {
    found.add("bulk");
  }
  return found;
}

beforeAll(async () => {
  await import("../src/pages/Records");
  await import("../src/pages/Matrix");
  await import("../src/pages/Provider");
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

  test("only a model's tool and an overview card are excused paging, and only a fact is excused an order", () => {
    // What breaks if this is deleted: the table quietly regrowing the excuses M27.8.6 removed. Every
    // list but the records route pages, searches and filters, except a card on an overview whose
    // link goes to a screen that does all three over the same route, and the owner's Models screen,
    // which he drew whole and which still pages; and the only lists not ordered by the reader are
    // the ones whose order is a fact rather than a preference.
    for (const [pattern, missing] of Object.entries(MISSING)) {
      const overview = OVERVIEW_CARDS[pattern];
      if (overview !== undefined) {
        const linked = MISSING[overview] ?? {};
        const wanted = DRAWN_WHOLE.has(overview) ? ["page"] : ["page", "search", "filter"];
        expect(wanted.filter((one) => one in linked), `${overview} behind ${pattern}`).toEqual([]);
        for (const capability of ["page", "search", "filter"] as const) {
          expect(missing[capability], `${pattern} ${capability}`).toBe(AN_OVERVIEW_CARD_LINKS_TO_ITS_LIST);
        }
        continue;
      }
      if (DRAWN_WHOLE.has(pattern)) {
        expect("page" in missing, pattern).toBe(false);
        expect([missing.search, missing.filter], pattern).toEqual([THE_OWNER_DREW_IT_WHOLE, THE_OWNER_DREW_IT_WHOLE]);
      } else if (!(pattern in THROUGH_A_MODELS_TOOL)) {
        expect(["page", "search", "filter"].filter((one) => one in missing), pattern).toEqual([]);
      }
      if (pattern in THROUGH_A_MODELS_TOOL) {
        const reason = THROUGH_A_MODELS_TOOL[pattern];
        for (const capability of ["page", "search", "filter"] as const) {
          expect([reason, EVERY_COLUMN_HAS_A_FILTER_BOX], `${pattern} ${capability}`).toContain(
            missing[capability] ?? reason,
          );
        }
      }
      if ("sort" in missing) {
        expect([ROW_PLANE_HAS_NO_ORDER, CHAIN_IN_ORDER, A_DOCUMENT_HAS_ONE_ORDER, THE_PROVIDERS_KEEP_THE_PRODUCTS_ORDER]).toContain(
          missing.sort,
        );
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
