/**
 * What the Memory screen asks the API for, what a remembered statement is, and how a person's
 * reference is checked before it is asked about. No React.
 *
 * **The design has no company-level memory screen, and this is why there is one.** SCREEN 13 of
 * `docs/screens.html` draws Memory as an item in the menu inside one agent and as a card on that
 * agent's page: curated beside extracted, the last revision, and a link to the change history.
 * `brain.console.screens` registers Memory under Govern, and the decision it is served by,
 * `brain.console.govern_estate.subject_memory`, is keyed by the person a memory is about rather
 * than by an agent. Neither memory table records which agent was running when a memory formed, so
 * a tab inside an agent would have nothing to select on. So the screen sits in Govern, is opened
 * for one person at a time, and draws the design's memory card and its change history for them.
 *
 * **One person at a time, and nothing lists whose memory exists.** `subject_memory` requires a
 * subject and has no value meaning everybody, because a list of the people the system remembers
 * things about is a directory of people. The page therefore asks for a reference and never offers
 * a list to pick from. See `brain.console.govern_estate.
 * A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE`.
 *
 * **The reference is checked here before it is sent, and the API checks it again.** The route
 * refuses an empty reference, one with white space in it, and one longer than a principal id can
 * be, with a 422 naming the parameter. That sentence is the least useful one this console has, so
 * `referenceProblem` says what is wrong in words first and the request is never made. The API's
 * check is the one that holds; this one is so a person is told what to fix.
 *
 * **Nothing on the answer varies with how much is remembered about somebody.** A person with
 * memories this reader may not recall and a person nobody remembers anything about are the same
 * response, and there is no truncation flag: the load is bounded by `considered_per_kind`, a
 * constant the page states for every person alike.
 *
 * Served by `brain.console.govern_estate` and `brain.console.reach_view`, through
 * `brain.estate_routes`.
 *
 * Task ids: M27.7.22
 */

import type { components } from "../api/schema";

export type RememberedText = components["schemas"]["MemoryTextView"];
export type Revision = components["schemas"]["RevisionView"];

/** Where the API keeps this screen. */
export const MEMORY_API_PATH = "/govern/memory";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const MEMORY_PATH = "/memory";

/** The one query parameter the route declares. */
export const SUBJECT_PARAMETER = "subject";

/**
 * The longest reference the route admits. `brain.tables.memory.PRINCIPAL_ID_CHARS`, which
 * `tests/estate-pages.test.tsx` reads out of the API's own document rather than trusting here.
 */
export const REFERENCE_CHARS = 64;

/** The request for one person's memory. */
export function memoryApiPath(subject: string): string {
  return `${MEMORY_API_PATH}?${SUBJECT_PARAMETER}=${encodeURIComponent(subject)}`;
}

/**
 * The console address for one person's memory.
 *
 * A literal first segment and an encoded reference, for `governQuery.subjectAddress`' reason:
 * GHSA-wrjc-x8rr-h8h6 is an open redirect through a backslash reaching `<Link>` and
 * `useNavigate`, and what holds the defence up is the constant prefix.
 */
export function memoryAddress(subject: string): string {
  return `${MEMORY_PATH}/${encodeURIComponent(subject)}`;
}

/** What is wrong with a typed reference, in words, or null when it may be asked about. */
export function referenceProblem(value: string): string | null {
  if (value.length === 0) {
    return "Enter the reference of the person whose memory you want to read.";
  }
  if (/\s/.test(value)) {
    return "A person's reference has no spaces in it. Check it and enter it again.";
  }
  if (value.length > REFERENCE_CHARS) {
    return `A person's reference is at most ${String(REFERENCE_CHARS)} characters long.`;
  }
  return null;
}

/** One person's memory, as this console holds it. */
export interface MemoryPage {
  readonly subject: string;
  readonly curated: readonly RememberedText[];
  readonly extracted: readonly RememberedText[];
  readonly history: readonly Revision[];
  readonly consideredPerKind: number;
  readonly staleness: string | null;
  readonly editIsNotWritable: boolean;
}

function nothing(subject: string): MemoryPage {
  return {
    subject,
    curated: [],
    extracted: [],
    history: [],
    consideredPerKind: 0,
    staleness: null,
    // True on an unreadable body, for `readSkillsPage`' reason.
    editIsNotWritable: true,
  };
}

/** Read `brain.estate_routes.SubjectMemoryView` out of a response body. */
export function readMemoryPage(payload: unknown, subject: string): MemoryPage {
  if (typeof payload !== "object" || payload === null) {
    return nothing(subject);
  }
  const body = payload as {
    subject_id?: unknown;
    curated?: unknown;
    extracted?: unknown;
    history?: unknown;
    considered_per_kind?: unknown;
    staleness?: unknown;
    edit_is_not_writable?: unknown;
  };
  if (!Array.isArray(body.curated) || !Array.isArray(body.extracted)) {
    return nothing(subject);
  }
  const staleness = body.staleness as { message?: unknown } | null | undefined;
  return {
    subject: typeof body.subject_id === "string" ? body.subject_id : subject,
    curated: body.curated as RememberedText[],
    extracted: body.extracted as RememberedText[],
    history: Array.isArray(body.history) ? (body.history as Revision[]) : [],
    consideredPerKind:
      typeof body.considered_per_kind === "number" ? body.considered_per_kind : 0,
    staleness: typeof staleness?.message === "string" ? staleness.message : null,
    editIsNotWritable: body.edit_is_not_writable !== false,
  };
}

/**
 * The size of what these statements say, in kilobytes to one decimal place, as the design's
 * memory card states it. Measured in UTF-8 bytes, which is what a statement costs to store and
 * to hand to a model, and over the statements shown and nothing else.
 */
export function kilobytes(texts: readonly RememberedText[]): string {
  const bytes = texts.reduce((sum, one) => sum + new TextEncoder().encode(one.statement).length, 0);
  return (bytes / 1024).toFixed(1);
}

/** The newest step in the history, or null. The API sends it oldest first. */
export function latestRevision(history: readonly Revision[]): Revision | null {
  return history.length === 0 ? null : (history[history.length - 1] ?? null);
}

/** The date part of an instant the API sent, which is all the design's card shows. */
export function dayOf(instant: string): string {
  return instant.slice(0, 10);
}
