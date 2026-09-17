/**
 * What the Sessions screen asks the API for, what it may send, and what its filters may offer. No
 * React.
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
 * **The list is searched, filtered, ordered and paged by the route** (`brain.listing`, over the
 * sessions the reader may see), and a filter offers only the values on rows already drawn. See
 * `components/listing.ts`' `A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN`.
 *
 * **Several sessions are ended by one confirmed request that ends each of them alone.** The route
 * runs the single ending once per session and answers each one's outcome, and the page says, per
 * session, whether it was ended. A session that was not ended is said the same way whatever the
 * reason, because the route answers it the same way.
 *
 * **No number about the rows.** `readSessionsPage` drops nothing because the answer carries no
 * total, and the page renders no count of sessions, including of the ones ticked.
 *
 * Task ids: M27.7.10, M27.8.6
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

/** One live session, as `brain.session_routes.SessionView` sends it. */
export type SessionRow = components["schemas"]["SessionView"];
/** One session's outcome in a bulk ending, as `brain.session_routes.SessionOutcome` sends it. */
export type SessionOutcome = components["schemas"]["SessionOutcome"];

/** Where the API keeps this screen and its controls. */
export const SESSIONS_API_PATH = "/govern/sessions";
export const END_SESSION_API_PATH = "/govern/sessions/end";
export const END_SESSIONS_API_PATH = "/govern/sessions/end-several";

/** The console address. */
export const SESSIONS_PATH = "/sessions";

/** The most sessions one bulk ending may name. `brain.listing.MAX_SEVERAL`; see the test. */
export const MOST_ENDED_AT_ONCE = 50;

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

/** The body of a bulk ending, as `SessionsEnding` declares it. One key. */
export interface SessionsEnding {
  readonly session_ids: readonly string[];
}

export function endingsBody(sessions: readonly SessionRow[]): SessionsEnding {
  return { session_ids: sessions.map((one) => one.session_id) };
}

/** Read `brain.session_routes.SessionsEnded` out of a response body. */
export function readOutcomes(payload: unknown): readonly SessionOutcome[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const outcomes = (payload as { outcomes?: unknown }).outcomes;
  return Array.isArray(outcomes) ? (outcomes as SessionOutcome[]) : [];
}

/** Whether a row may be ticked for a bulk ending: the API said it may be ended, and it is not yours. */
export function tickable(row: SessionRow): boolean {
  return row.endable && !row.yours;
}

/** The filters the Sessions route declares that this screen offers. */
export const SESSION_FILTERS: readonly FilterChoice<SessionRow>[] = [
  {
    column: "department",
    label: "Department",
    everything: "All departments",
    read: (row) => row.department,
  },
  { column: "principal_id", label: "Person", everything: "Everyone", read: (row) => row.principal_id },
  {
    column: "second_factor",
    label: "Second factor",
    everything: "With or without",
    read: (row) => row.second_factor,
    describe: (value) => (value === "true" ? "Shown" : "Not shown"),
  },
];

/** The orders this screen offers, as the route spells them. Empty is the route's own. */
export const SESSION_SORTS: readonly SortChoice[] = [
  { value: "", label: "Most recent sign-in first" },
  { value: "display_name", label: "By name" },
  { value: "department", label: "By department" },
  { value: "lapses_at", label: "Soonest to end first" },
];

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

/** The question the bulk confirmation asks. Names no figure: the list under it names each one. */
export const END_SELECTED_QUESTION = "End each of these sessions?";

/** What the bulk confirmation lists for one session: whose, from when, and what happens to it. */
export function endingLine(row: SessionRow): string {
  return `${row.display_name}'s session from ${when(row.signed_in_at)} is refused from its next request.`;
}

/** What the page says about one session after a bulk ending. */
export function outcomeLine(row: SessionRow | undefined, outcome: SessionOutcome): string {
  const whose = row === undefined ? "A session" : `${row.display_name}'s session`;
  return outcome.ended ? `${whose} was ended.` : `${whose} was not ended.`;
}
