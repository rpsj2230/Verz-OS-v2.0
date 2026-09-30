/**
 * Adding knowledge by link and many documents at once, as this console holds the API's answers.
 *
 * `brain.knowledge_intake_routes` serves both. A link is posted as JSON with the address in the
 * body, never in the query string, because a share link carries its token and a URL is written into
 * every access log. A queued file is posted exactly as `knowledgeQuery.uploadPath` posts one file,
 * raw with its name in a header, to the queued route; the answer is a ticket, and what became of the
 * file is asked of the ticket afterwards, because the worker reads it after the request has ended.
 *
 * Nothing here decides who may add what. The kinds, the departments and whether the person's own
 * level is offered all come from `GET /knowledge/uploads/options`, the same answer the Add a document
 * card is drawn from.
 *
 * **A file queued behind others is told its place and expected wait** (M22.1.4). The answer to the
 * upload carries both as numbers and in its sentence, which is what the form shows; a later look at
 * the ticket carries neither, because a place is true when it is given and nothing keeps it current.
 *
 * Task ids: M7.1.2, M7.1.5, M22.2.4, M22.1.4
 */

import { UPLOADS_API_PATH, type UploadLevel } from "./knowledgeQuery";

/** Where a link is added. */
export const LINKS_API_PATH = "/knowledge/links";

/** Where one file of a bulk upload is queued, and where each queued file's outcome is asked. */
export const QUEUED_API_PATH = `${UPLOADS_API_PATH}/queued`;

/** What a link form holds before it is sent. */
export interface LinkDraft {
  readonly url: string;
  readonly kind: string;
  readonly level: UploadLevel;
  readonly department: string;
}

/** Said beside a field left empty, or an address the API would refuse before it fetched anything. */
export const LINK_PROBLEMS = {
  url: "Paste the page's whole address as your browser shows it, beginning with https.",
  kind: "Choose what kind of document this page is.",
  department: "Choose the department it is for.",
} as const;
export type LinkProblem = keyof typeof LINK_PROBLEMS;

/**
 * What is wrong with a link draft before it is sent. Only what a person can see is blank or not an
 * https address; whether the address is safe to fetch is the API's to judge, on every hop.
 */
export function linkProblems(draft: LinkDraft): LinkProblem[] {
  const found: LinkProblem[] = [];
  if (!/^https:\/\/\S+$/i.test(draft.url.trim())) {
    found.push("url");
  }
  if (draft.kind === "") {
    found.push("kind");
  }
  if (draft.level === "department" && draft.department === "") {
    found.push("department");
  }
  return found;
}

/** The body a link is posted with: `brain.knowledge_intake_routes.LinkAsked`. */
export function linkBody(draft: LinkDraft): {
  readonly url: string;
  readonly kind: string;
  readonly level: UploadLevel;
  readonly department: string;
} {
  return {
    url: draft.url.trim(),
    kind: draft.kind,
    level: draft.level,
    department: draft.level === "department" ? draft.department : "",
  };
}

/** The address one file of a bulk upload is queued at: closed-list words and a slug, never a name. */
export function queuedPath(kind: string, level: UploadLevel, department: string): string {
  const query = new URLSearchParams({ kind, level, department: level === "department" ? department : "" });
  return `${QUEUED_API_PATH}?${query.toString()}`;
}

/** Where one queued file's outcome is asked. The ticket is the API's, forty hex characters. */
export function queuedTicketPath(ticket: string): string {
  return `${QUEUED_API_PATH}/${encodeURIComponent(ticket)}`;
}

/** The three states a queued file can be in, as `brain.knowledge.ingest_queue.TicketState` names them. */
export const QUEUED_STATES = ["queued", "added", "not_added"] as const;
export type QueuedState = (typeof QUEUED_STATES)[number];

/** `brain.knowledge_intake_routes.QueuedView`, as this console holds it. */
export interface Queued {
  readonly ticket: string;
  readonly name: string;
  readonly state: QueuedState;
  /** The API's own sentence about the file, the cause included when it was not added, and its
   * place and expected wait when it was just queued behind others. */
  readonly said: string;
  readonly itemId: string | null;
  /** Where it stood in line when it was sent, or null when it starts as soon as the worker is free. */
  readonly position: number | null;
  /** The expected wait before it starts, in seconds, beside `position`. An estimate, not a promise. */
  readonly expectedWaitSeconds: number | null;
}

/**
 * Every field `brain.knowledge_intake_routes.QueuedView` sends, held against the Python so a new
 * one is noticed rather than dropped. `readQueued` reads all of them but `passages`, a count of the
 * sender's own document that the form does not show.
 */
export const QUEUED_FIELDS = [
  "ticket",
  "name",
  "state",
  "said",
  "item_id",
  "passages",
  "position",
  "expected_wait_seconds",
] as const;

/** Read `QueuedView` out of a response body, or null when it is not one. */
export function readQueued(payload: unknown): Queued | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  const state = QUEUED_STATES.find((one) => one === body.state);
  if (typeof body.ticket !== "string" || typeof body.name !== "string" || typeof body.said !== "string" || !state) {
    return null;
  }
  return {
    ticket: body.ticket,
    name: body.name,
    state,
    said: body.said,
    itemId: typeof body.item_id === "string" ? body.item_id : null,
    position: typeof body.position === "number" ? body.position : null,
    expectedWaitSeconds: typeof body.expected_wait_seconds === "number" ? body.expected_wait_seconds : null,
  };
}
