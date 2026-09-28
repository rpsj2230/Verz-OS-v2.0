/**
 * What the Sessions page asks the API for, what its two writes send, and the words it builds from
 * the answers. No React.
 *
 * **Who may see or end a session is the server's decision.** The listing is `brain.console.govern.
 * open_sessions`' answer and `endable` is `may_end`'s, both computed per request; this module only
 * decides whether a control is drawn, and the route decides again when it is pressed. Several
 * sessions are ended by one request that the route runs as that many single endings, answering
 * each one's outcome, and a session that was not ended is said the same way whatever the reason.
 *
 * **No number about the rows.** The answer carries no total and the page draws none.
 *
 * Task ids: M27.7.10, M27.8.6, M27.16.1
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

/** One live session, as `brain.session_routes.SessionView` sends it. */
export type SessionRow = components["schemas"]["SessionView"];
/** One session's outcome in a bulk ending, as `brain.session_routes.SessionOutcome` sends it. */
export type SessionOutcome = components["schemas"]["SessionOutcome"];

/** Where the API keeps this page and its controls. */
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
  /** The route's load came back full. Never how much more there is. */
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

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * One row out of the answer, or null. Carried only with its id, a name and both instants, and
 * with the three flags read as true only when the API said true, so a missing `endable` never
 * draws a control.
 */
function readSession(item: unknown): SessionRow | null {
  if (typeof item !== "object" || item === null || Array.isArray(item)) {
    return null;
  }
  // A cast at the boundary: every field is read back through a type check below.
  const entry = item as Readonly<Record<string, unknown>>;
  const id = text(entry["session_id"]);
  const name = text(entry["display_name"]);
  const signedIn = text(entry["signed_in_at"]);
  const lapses = text(entry["lapses_at"]);
  if (id === "" || name === "" || signedIn === "" || lapses === "") {
    return null;
  }
  const department = entry["department"];
  return {
    session_id: id,
    principal_id: text(entry["principal_id"]),
    display_name: name,
    department: typeof department === "string" && department !== "" ? department : null,
    second_factor: entry["second_factor"] === true,
    signed_in_at: signedIn,
    lapses_at: lapses,
    yours: entry["yours"] === true,
    endable: entry["endable"] === true,
  };
}

/** Read `brain.session_routes.SessionsPage` out of a response body. Each session once, in order. */
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
  const seen = new Set<string>();
  const sessions: SessionRow[] = [];
  for (const item of body.items as readonly unknown[]) {
    const row = readSession(item);
    if (row !== null && !seen.has(row.session_id)) {
      seen.add(row.session_id);
      sessions.push(row);
    }
  }
  return {
    sessions,
    truncated: body.truncated === true,
    ending: text(body.ending),
    appears: text(body.appears),
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

/** The instant a single ending was recorded, or null when the answer carried none. */
export function readEndedAt(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const ended = (payload as { ended_at?: unknown }).ended_at;
  return typeof ended === "string" && ended !== "" ? ended : null;
}

/** Whether a row may be ended from this page: the API said it may be, and it is not yours. */
export function tickable(row: SessionRow): boolean {
  return row.endable && !row.yours;
}

/** Whether a second factor was shown for the session, in words. */
export function factorWords(row: SessionRow): string {
  return row.second_factor ? "Yes" : "No";
}

/** The filters the Sessions route declares that this page offers, over values on rows drawn. */
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
    describe: (value) => (value === "true" ? "Yes" : "No"),
  },
];

/** The orders this page offers, as the route spells them. Empty is the route's own. */
export const SESSION_SORTS: readonly SortChoice[] = [
  { value: "", label: "Newest sign-in first" },
  { value: "display_name", label: "Name" },
  { value: "department", label: "Department" },
  { value: "lapses_at", label: "Ending soonest first" },
];

/** An instant, as the rows show it. Other pages borrow it. */
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

/** What the bulk confirmation lists for one session: whose, and from when. */
export function endingLine(row: SessionRow): string {
  return `${row.display_name}, signed in ${when(row.signed_in_at)}`;
}

/** What a single ending says once it is done: whose, and the instant the database recorded. */
export function endedSentence(row: SessionRow, endedAt: string | null): string {
  const at = endedAt === null ? "" : ` at ${when(endedAt)}`;
  return `${row.display_name}'s session was ended${at}. The next request made with it is refused.`;
}

/** What the page says about one session after a bulk ending. */
export function outcomeLine(row: SessionRow | undefined, outcome: SessionOutcome): string {
  const whose = row === undefined ? "A session" : `${row.display_name}'s session`;
  return outcome.ended ? `${whose} was ended.` : `${whose} was not ended.`;
}
