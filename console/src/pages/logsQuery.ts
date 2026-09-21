/**
 * What the Logs screen asks the API for and says. No React.
 *
 * `brain.log_routes` answers the warnings and errors this install kept, newest first, one page at a
 * time. `brain.ops.log_capture` decided on the way in what a row may carry: an event name only when
 * it was written in the source, a field in the clear only when it is system vocabulary, a field's
 * shape otherwise, and an exception's type and never its message. So nothing here hides a value,
 * because no value arrives, and nothing here decides who may read: the API refuses a reader who may
 * not, and the page shows that refusal in the API's own words.
 *
 * **No number about the log is rendered.** Not a total and not "showing". A row's repeat count is a
 * fact about that row, and a page ends with a cursor or with a sentence saying there is no more.
 *
 * **The address is the state**, as on the Audit screen: the level, the search and the period are
 * query parameters of the console address, so an administrator can send a colleague the view they
 * are looking at. The cursor is not, because it is a position in one reader's page.
 *
 * Task ids: M27.8.14, M27.8.6
 */

import type { components } from "../api/schema";

/** One page, as `brain.log_routes.LogPage` sends it. */
export type LogPageBody = components["schemas"]["LogPage"];
/** One row, as `LogEntryView` sends it. */
export type LogEntry = components["schemas"]["LogEntryView"];

export const LOGS_API_PATH = "/logs";
export const LOGS_PATH = "/logs";
export const LOGS_LABEL = "Logs";
export const LOGS_CRUMB = "Operate › Logs";
export const LOGS_LEDE =
  "Warnings and errors the application logged, newest first. Search by event name, narrow by level " +
  "and period, and quote a reference to find the request it belongs to on the Errors screen.";

/** Said once, above the rows. */
export const NO_VALUE_IS_KEPT =
  "A value in a log line is never kept. A field shows its name, and its value only when it is one of " +
  "the product's own words or numbers; anything else shows as its shape. An exception shows its type " +
  "and never its message.";

export const READING_THE_LOG = "Reading the log.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no row is listed. The console and " +
  "the API are probably from different releases.";
export const NO_ENTRIES = "Nothing was kept for this search in this period.";
export const NO_MORE_ENTRIES = "There are no older rows for this search in this period.";
export const SHOW_OLDER = "Show older entries";
export const SHOW_NEWER = "Show newer entries";

/** What an event with no kept name reads as. */
export const NAME_NOT_KEPT = "Name not kept";
export const NAME_NOT_KEPT_WHY =
  "This event's name was not written in the source, so it was not kept; its place in the source is.";

/** What the page cannot show, each sentence gated on the field the API sends. */
export const WHAT_IS_NOT_HERE_HEADING = "What this screen cannot show";
export const DEBUG_IS_NOT_KEPT = "Debug lines are never kept.";
export const INFO_IS_A_SAMPLE =
  "Information lines are kept as a small sample, so an information line missing here may still have been logged.";
export const WORKER_OUTPUT_IS_NOT_KEPT =
  "The background worker's own output stays on its container and is not kept here; a scheduled job " +
  "that failed is on the Errors screen.";

export function keptFor(days: number): string {
  return `A row is kept for ${String(days)} days once the retention sweep is released, and the oldest rows go first if the log reaches its ceiling.`;
}

/** The accessible names. */
export const SEARCH_LABEL = "Search the log";
export const FILTERS_LABEL = "Narrow the log";
export const ENTRIES_LABEL = "Log rows";

/** The console address's own parameter names. The API's are in `logsApiPath`. */
export const ADDRESS_PARAMETERS = {
  level: "level",
  event: "event",
  period: "period",
  order: "order",
} as const;

/** Which way the rows are walked, as `brain.log_routes.LogOrder` spells it. */
export const ORDERS = ["newest", "oldest"] as const;
export type Order = (typeof ORDERS)[number];

export const ORDER_LABELS: Readonly<Record<Order, string>> = Object.freeze({
  newest: "Newest first",
  oldest: "Oldest first",
});

/** The levels a row can be kept at, most severe first. Debug is not one of them. */
export const LEVELS = ["critical", "error", "warning", "info"] as const;
export type Level = (typeof LEVELS)[number];

export const LEVEL_LABELS: Readonly<Record<Level, string>> = Object.freeze({
  critical: "Critical",
  error: "Error",
  warning: "Warning",
  info: "Information",
});

export const ALL_LEVELS = "Every level";

/** The periods offered. A closed list, all inside the API's longest window. */
export const PERIODS = ["hour", "day", "week", "month"] as const;
export type Period = (typeof PERIODS)[number];

export const PERIOD_LABELS: Readonly<Record<Period, string>> = Object.freeze({
  hour: "Last hour",
  day: "Last 24 hours",
  week: "Last 7 days",
  month: "Last 30 days",
});

const PERIOD_HOURS: Readonly<Record<Period, number>> = Object.freeze({
  hour: 1,
  day: 24,
  week: 24 * 7,
  month: 24 * 30,
});

/** The longest search the API accepts, `brain.ops.log_capture.MAX_EVENT_CHARS`. */
export const MAX_SEARCH_CHARS = 160;

/** How many rows one page asks for. Below the route's declared maximum. */
export const LOGS_PAGE_SIZE = 50;

export interface LogFilters {
  /** One level, or empty for every level. */
  readonly level: Level | "";
  /** A literal search within event names, or empty. */
  readonly event: string;
  readonly period: Period;
  readonly order: Order;
}

export const DEFAULT_FILTERS: LogFilters = Object.freeze({ level: "", event: "", period: "day", order: "newest" });

/** The filters a console address carries. Anything unrecognised is the default. */
export function filtersFrom(search: URLSearchParams): LogFilters {
  const level = search.get(ADDRESS_PARAMETERS.level) ?? "";
  const period = search.get(ADDRESS_PARAMETERS.period) ?? "";
  const order = search.get(ADDRESS_PARAMETERS.order) ?? "";
  return {
    order: (ORDERS as readonly string[]).includes(order) ? (order as Order) : DEFAULT_FILTERS.order,
    level: (LEVELS as readonly string[]).includes(level) ? (level as Level) : DEFAULT_FILTERS.level,
    event: (search.get(ADDRESS_PARAMETERS.event) ?? "").trim().slice(0, MAX_SEARCH_CHARS),
    period: (PERIODS as readonly string[]).includes(period) ? (period as Period) : DEFAULT_FILTERS.period,
  };
}

/** The console address with one filter set, or removed when `value` is empty. */
export function withFilter(search: URLSearchParams, name: string, value: string): string {
  const next = new URLSearchParams(search);
  if (value === "") {
    next.delete(name);
  } else {
    next.set(name, value);
  }
  const query = next.toString();
  return query === "" ? LOGS_PATH : `${LOGS_PATH}?${query}`;
}

/**
 * The whole request one page makes. `start` and `end` carry their offset, because the route refuses
 * a naive instant, and the end is fixed when the filters are so fetching older rows does not move the
 * window under the rows already shown.
 */
export function logsApiPath(filters: LogFilters, now: Date, cursor: string | null): string {
  const query = new URLSearchParams();
  query.set("limit", String(LOGS_PAGE_SIZE));
  query.set("start", new Date(now.getTime() - PERIOD_HOURS[filters.period] * 60 * 60 * 1000).toISOString());
  query.set("end", now.toISOString());
  if (filters.level !== "") {
    query.set("level", filters.level);
  }
  if (filters.event !== "") {
    query.set("event", filters.event);
  }
  if (filters.order !== DEFAULT_FILTERS.order) {
    query.set("order", filters.order);
  }
  if (cursor !== null) {
    query.set("cursor", cursor);
  }
  return `${LOGS_API_PATH}?${query.toString()}`;
}

/** One page, as this console holds it. */
export interface LogPage {
  readonly entries: readonly LogEntry[];
  readonly nextCursor: string | null;
  readonly keptForDays: number;
  readonly debugIsNotKept: boolean;
  readonly infoIsASample: boolean;
  readonly workerOutputIsNotKept: boolean;
}

/** A page from the API's answer, or null when the answer is not one. */
export function readLogPage(payload: unknown): LogPage | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<LogPageBody>;
  if (!Array.isArray(body.items)) {
    return null;
  }
  return {
    entries: body.items,
    nextCursor: typeof body.next_cursor === "string" ? body.next_cursor : null,
    keptForDays: typeof body.kept_for_days === "number" ? body.kept_for_days : 0,
    debugIsNotKept: body.debug_is_not_kept !== false,
    infoIsASample: body.info_is_a_sample !== false,
    workerOutputIsNotKept: body.worker_output_is_not_kept !== false,
  };
}

/** How often a row's call happened, in words, or nothing for once. */
export function repeated(times: number): string {
  return times > 1 ? `${String(times)} times` : "";
}
