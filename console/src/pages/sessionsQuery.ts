/**
 * What the Sessions screen asks the API for, what it may send, and how its rows narrow. No React.
 *
 * **This screen sits beside People and grants in Govern, which is where `docs/screens.html` SCREEN
 * 10 puts what happens to a person's sign-ins.** The design draws a leaver's line as "sessions
 * killed, tokens rotated" under the organisation tree; the registry's Sessions screen is that
 * sentence made into a list with the control on it.
 *
 * **Nothing here decides who may see or end a session.** The listing is `brain.console.govern.
 * open_sessions`' answer and `endable` is `may_end`'s, both computed on the server per request;
 * this module reads them and decides only what a control looks like. A session this reader may
 * not end has no button, and the route refuses the end whatever the page drew.
 *
 * **The filters narrow what was shown and offer only what was shown.** Department and person are
 * the two axes every console screen carries, and the values offered are the ones on the rows the
 * API sent, so a dropdown cannot name a department this reader was not shown a session in. See
 * `A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`.
 *
 * **No number about the rows.** `readSessionsPage` drops nothing because the answer carries no
 * total, and the page renders no count of sessions.
 *
 * Task ids: M27.7.10
 */

import type { components } from "../api/schema";

/** One live session, as `brain.session_routes.SessionView` sends it. */
export type SessionRow = components["schemas"]["SessionView"];

/** Written down because the obvious dropdown lists every department in the company. */
export const A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE =
  "The department and person filters narrow the rows already on the page and offer the values " +
  "those rows carry. A list of departments read from anywhere else would name places this reader " +
  "was not shown a session in, which is the listing the rows were narrowed to avoid.";

/** Where the API keeps this screen and its control. */
export const SESSIONS_API_PATH = "/govern/sessions";
export const END_SESSION_API_PATH = "/govern/sessions/end";

/** The console address. */
export const SESSIONS_PATH = "/sessions";

/** How many sessions one listing asks for. Below the route's maximum; see the test. */
export const SESSIONS_PAGE_SIZE = 200;

export function sessionsApiPath(): string {
  return `${SESSIONS_API_PATH}?limit=${String(SESSIONS_PAGE_SIZE)}`;
}

/** One page of sessions, as this console holds it. */
export interface SessionsPage {
  readonly sessions: readonly SessionRow[];
  readonly truncated: boolean;
  /** What ending a session does, in the API's words. */
  readonly ending: string;
  /** When a session appears, in the API's words. */
  readonly appears: string;
}

const NO_SESSIONS: SessionsPage = Object.freeze({
  sessions: [],
  truncated: false,
  ending: "",
  appears: "",
});

/** Read `brain.session_routes.SessionsPage` out of a response body. */
export function readSessionsPage(payload: unknown): SessionsPage {
  if (typeof payload !== "object" || payload === null) {
    return NO_SESSIONS;
  }
  const body = payload as {
    items?: unknown;
    truncated?: unknown;
    ending?: unknown;
    appears?: unknown;
  };
  if (!Array.isArray(body.items)) {
    return NO_SESSIONS;
  }
  return {
    sessions: body.items as SessionRow[],
    truncated: body.truncated === true,
    ending: typeof body.ending === "string" ? body.ending : "",
    appears: typeof body.appears === "string" ? body.appears : "",
  };
}

/** The body of one ending, as `SessionEnding` declares it. One key. */
export interface SessionEnding {
  readonly session_id: string;
}

export function endingBody(session: SessionRow): SessionEnding {
  return { session_id: session.session_id };
}

/** How the rows may be put in order. */
export const SORTS = ["recent", "name"] as const;
export type Sort = (typeof SORTS)[number];
export const SORT_LABELS: Readonly<Record<Sort, string>> = Object.freeze({
  recent: "Most recent sign-in first",
  name: "By name",
});

/** What a reader narrowed the page to. Empty strings are unset. */
export interface SessionFilters {
  readonly department: string;
  readonly person: string;
  readonly sort: Sort;
}

export const NO_SESSION_FILTERS: SessionFilters = Object.freeze({
  department: "",
  person: "",
  sort: "recent",
});

/** The department a row carries, as a filter value. A person in no department is "". */
export function departmentOf(row: SessionRow): string {
  return row.department ?? "";
}

/** The departments on these rows, each once, in name order. See the module note. */
export function offeredDepartments(rows: readonly SessionRow[]): readonly string[] {
  return [...new Set(rows.map(departmentOf).filter((one) => one !== ""))].sort();
}

/** The people on these rows, each once, by name. */
export function offeredPeople(
  rows: readonly SessionRow[],
): readonly { id: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const row of rows) {
    seen.set(row.principal_id, row.display_name);
  }
  return [...seen.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

/** The rows these filters keep, in the order asked for. */
export function narrowed(rows: readonly SessionRow[], filters: SessionFilters): readonly SessionRow[] {
  const kept = rows.filter(
    (row) =>
      (filters.department === "" || departmentOf(row) === filters.department) &&
      (filters.person === "" || row.principal_id === filters.person),
  );
  if (filters.sort === "name") {
    return [...kept].sort(
      (a, b) => a.display_name.localeCompare(b.display_name) || a.session_id.localeCompare(b.session_id),
    );
  }
  return [...kept].sort((a, b) => b.signed_in_at.localeCompare(a.signed_in_at));
}

/** An instant, as the rows show it. */
export function when(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The question the confirmation asks, naming the person and when they signed in. */
export function endQuestion(row: SessionRow): string {
  return `End ${row.display_name}'s session from ${when(row.signed_in_at)}?`;
}
