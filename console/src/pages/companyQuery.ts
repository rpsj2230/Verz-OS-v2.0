/**
 * What the company pages ask the API for, and how each answer is read. No React.
 *
 * Three reads, each decided by `brain.console.global_surfaces` and served by `brain.company_routes`:
 * the estate (every agent, skill, knowledge item and connector the reader may know exists), all
 * activity, and what the company spent. **Nothing is filtered, totalled or counted here.** The
 * department and person filters are query parameters the API applies after its own visibility
 * check, so a filter the browser applied would be a second answer to what the reader may see, and
 * the copy in the browser is the one somebody edits.
 *
 * **A filter offers what the answer carried and nothing else**, which is
 * `brain.company_routes.A_FILTER_OFFERS_ONLY_WHAT_THE_ROWS_ALREADY_SAID`: the departments and the
 * people come from the body, and a chosen value is kept offered so a narrowed list that came back
 * empty still says what it is set to.
 *
 * **Withheld is drawn as withheld.** A consumption answer that says `withheld` carries no figure,
 * and this module gives the page nothing to draw a figure from: `readConsumption` returns no total
 * for it rather than a nought.
 *
 * Task ids: M33.1.1.1, M33.1.1.2, M33.1.1.3
 */

import type { components } from "../api/schema";

export type EstateBody = components["schemas"]["EstateView"];
export type EstateItem = components["schemas"]["EstateRowView"];
export type ActivityBody = components["schemas"]["CompanyActivityPage"];
export type ConsumptionBody = components["schemas"]["ConsumptionView"];

/** Where the API keeps each read. */
export const ESTATE_API_PATH = "/company/estate";
export const ACTIVITY_API_PATH = "/company/activity";
export const CONSUMPTION_API_PATH = "/company/consumption";

/** The console addresses. */
export const ESTATE_PATH = "/company/estate";
export const ACTIVITY_PATH = "/company/activity";
export const CONSUMPTION_PATH = "/company/consumption";

/** The query parameters the routes declare, which the page keeps in its own address too. */
export const PARAMETERS = Object.freeze({
  department: "department",
  person: "person",
  kind: "kind",
  cursor: "cursor",
  days: "days",
  search: "q",
  order: "order",
});

/** The two directions the activity route walks the ledger in, newest first unless asked. */
export const ORDERS = ["newest", "oldest"] as const;
export const ORDER_WORDS: Readonly<Record<string, string>> = Object.freeze({
  newest: "Newest first",
  oldest: "Oldest first",
});

/** The four kinds, in the words a person reads them in. */
export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  agent: "Agent",
  skill: "Skill",
  knowledge: "Knowledge",
  connector: "Connector",
});

/** The windows the consumption page offers, each inside the route's own bound. */
export const CONSUMPTION_WINDOWS = [7, 30, 90] as const;
export const DEFAULT_WINDOW = 30;

/** An API address with the named parameters set, in a fixed order, and the empty ones left out. */
export function withParameters(path: string, values: Readonly<Record<string, string>>): string {
  const query = new URLSearchParams();
  for (const name of Object.keys(values).sort()) {
    const value = values[name] ?? "";
    if (value !== "") {
      query.set(name, value);
    }
  }
  const written = query.toString();
  return written === "" ? path : `${path}?${written}`;
}

/** The estate's address for the filters in the page's own address. */
export function estateApiPath(search: URLSearchParams): string {
  return withParameters(ESTATE_API_PATH, {
    [PARAMETERS.department]: search.get(PARAMETERS.department) ?? "",
    [PARAMETERS.person]: search.get(PARAMETERS.person) ?? "",
    [PARAMETERS.kind]: search.get(PARAMETERS.kind) ?? "",
  });
}

/** All activity's address for the filters in the page's own address, from `cursor` when given. */
export function activityApiPath(search: URLSearchParams, cursor = ""): string {
  return withParameters(ACTIVITY_API_PATH, {
    [PARAMETERS.department]: search.get(PARAMETERS.department) ?? "",
    [PARAMETERS.person]: search.get(PARAMETERS.person) ?? "",
    [PARAMETERS.search]: (search.get(PARAMETERS.search) ?? "").trim(),
    [PARAMETERS.order]: search.get(PARAMETERS.order) ?? "",
    [PARAMETERS.cursor]: cursor,
  });
}

/** The consumption's address for a window of `days`. */
export function consumptionApiPath(days: number): string {
  return withParameters(CONSUMPTION_API_PATH, { [PARAMETERS.days]: String(days) });
}

/** A chosen value kept offered, so a filter that came back empty still says what it is set to. */
export function keepChosen(values: readonly string[], chosen: string): readonly string[] {
  return chosen === "" || values.includes(chosen) ? values : [chosen, ...values];
}

/** The page's own address with one parameter changed, and the cursor dropped with it. */
export function narrowedTo(base: string, search: URLSearchParams, name: string, value: string): string {
  const next = new URLSearchParams(search);
  next.delete(PARAMETERS.cursor);
  if (value === "") {
    next.delete(name);
  } else {
    next.set(name, value);
  }
  const written = next.toString();
  return written === "" ? base : `${base}?${written}`;
}

/** An estate answer, or null when the body is not one. */
export function readEstate(payload: unknown): EstateBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<EstateBody>;
  if (!Array.isArray(body.items) || !Array.isArray(body.departments) || !Array.isArray(body.people)) {
    return null;
  }
  return body as EstateBody;
}

/** An activity page, or null when the body is not one. */
export function readActivity(payload: unknown): ActivityBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<ActivityBody>;
  if (!Array.isArray(body.items) || !Array.isArray(body.departments) || !Array.isArray(body.actors)) {
    return null;
  }
  return body as ActivityBody;
}

/** What the consumption page may draw: a figure and its lines, or that the figure is withheld. */
export type Consumption =
  | { readonly withheld: true; readonly since: string; readonly until: string }
  | {
      readonly withheld: false;
      readonly since: string;
      readonly until: string;
      readonly currency: string;
      readonly spendMinor: number;
      readonly lines: readonly { readonly department: string; readonly spendMinor: number }[];
      readonly incomplete: boolean;
      readonly ceilingSet: boolean;
    };

/**
 * A consumption answer, or null when the body is not one. A withheld answer carries no figure here,
 * whatever else the body holds, so a page cannot draw one for it.
 */
export function readConsumption(payload: unknown): Consumption | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<ConsumptionBody>;
  if (typeof body.since !== "string" || typeof body.until !== "string" || typeof body.withheld !== "boolean") {
    return null;
  }
  if (body.withheld) {
    return { withheld: true, since: body.since, until: body.until };
  }
  if (typeof body.spend_minor !== "number" || !Array.isArray(body.by_department)) {
    return null;
  }
  return {
    withheld: false,
    since: body.since,
    until: body.until,
    currency: typeof body.currency === "string" ? body.currency : "",
    spendMinor: body.spend_minor,
    lines: body.by_department.map((one) => ({ department: one.department, spendMinor: one.spend_minor })),
    incomplete: body.incomplete === true,
    ceilingSet: body.ceiling_set === true,
  };
}
