/**
 * What the Access requests screen asks for and says. No React.
 *
 * `brain.access_request_routes` holds both halves. A person asks for a field they were shown locked,
 * or a department an answer said was outside their scopes, and is told one sentence whatever
 * happened; the person who can decide reads the requests addressed to them, with the question in
 * the asker's words. The screen draws both, because everybody may ask and anybody may be an owner.
 *
 * **The reply is the API's sentence, drawn as sent.** `ASKER_ACKNOWLEDGEMENT` is one constant on the
 * server, and a console that wrote its own "sent to the Finance owner" would undo the one-way flow
 * the route exists to keep.
 *
 * Task ids: M4.3.4, M2.2.4
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

export type AccessRequestsBody = components["schemas"]["AccessRequestsPage"];
export type AccessRequestRow = components["schemas"]["AccessRequestView"];

export const ACCESS_REQUESTS_API_PATH = "/access-requests";
export const ACCESS_REQUESTS_PATH = "/access-requests";
export const ACCESS_REQUESTS_LABEL = "Access requests";
export const ACCESS_REQUESTS_CRUMB = "Use › Access requests";
export const ACCESS_REQUESTS_LEDE =
  "Ask for a field you were shown locked, or a department an answer said is outside your scopes. " +
  "Requests other people sent to you are listed below.";

export const ASK_HEADING = "Ask for access";
export const ASK_LABEL = "Send the request";
export const SENT_HEADING = "Requests sent to you";
export const SENT_CAPTION = "Requests addressed to you, newest first";
export const NOTHING_SENT = "Nobody has sent you a request.";
export const NONE_MATCH = "No request sent to you matches what you asked for.";
export const FILTERS_LABEL = "Narrow the requests sent to you";
export const READING_REQUESTS = "Reading the requests sent to you.";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no request is listed. The console " +
  "and the API are probably from different releases.";
export const FULL_LIST =
  "There are more requests sent to you than this page shows. Show more, or narrow the list.";

/** What the owner's list may be narrowed by, as `brain.access_request_routes.REQUESTS` declares. */
export const REQUEST_FILTERS: readonly FilterChoice<AccessRequestRow>[] = [
  {
    column: "asker_id",
    label: "Asked by",
    everything: "Anybody",
    read: (row) => row.asker_id,
  },
  {
    column: "subject",
    label: "About",
    everything: "Anything",
    read: (row) => row.subject,
  },
  {
    column: "requested_capability",
    label: "Would need",
    everything: "Any capability",
    read: (row) => row.requested_capability,
  },
];

export const REQUEST_SORTS: readonly SortChoice[] = [
  { value: "", label: "Most recently asked first" },
  { value: "asker_id", label: "By who asked" },
  { value: "subject", label: "By what it is about" },
];

/** What a request is about: a department, or a field on a kind of record. */
export type AskKind = "department" | "field";

export interface AccessAsk {
  readonly kind: AskKind;
  readonly department: string;
  readonly entity: string;
  readonly field: string;
  readonly question: string;
}

export const EMPTY_ASK: AccessAsk = Object.freeze({
  kind: "department",
  department: "",
  entity: "",
  field: "",
  question: "",
});

/** Said beside a field left blank, before anything is sent. */
export const ASK_BLANKS: Readonly<
  Record<"department" | "entity" | "field" | "question", string>
> = {
  department: "Name the department you need, as the answer named it.",
  entity: "Name the kind of record the locked field was on.",
  field: "Name the field that was shown locked.",
  question: "Say what you need it for, so whoever decides can judge.",
};

export function askBlanks(
  ask: AccessAsk,
): readonly (keyof typeof ASK_BLANKS)[] {
  const needed: (keyof typeof ASK_BLANKS)[] =
    ask.kind === "department"
      ? ["department", "question"]
      : ["entity", "field", "question"];
  return needed.filter((name) => ask[name].trim() === "");
}

/** The body `AccessAsked` takes: one subject and the question, nothing else. */
export function askBody(ask: AccessAsk): Record<string, string> {
  const question = ask.question.trim();
  return ask.kind === "department"
    ? { department: ask.department.trim().toLowerCase(), question }
    : {
        entity: ask.entity.trim().toLowerCase(),
        field: ask.field.trim().toLowerCase(),
        question,
      };
}

/** The API's reply sentence, or null when the answer carries none. */
export function acknowledgement(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const message = (payload as { message?: unknown }).message;
  return typeof message === "string" ? message : null;
}

/** A subject as the owner reads it: `department:finance` becomes "The finance department". */
export function subjectWords(subject: string): string {
  return subject.startsWith("department:")
    ? `The ${subject.slice("department:".length)} department`
    : subject;
}

export function readAccessRequests(
  payload: unknown,
): AccessRequestsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { items?: unknown; truncated?: unknown };
  if (!Array.isArray(body.items) || typeof body.truncated !== "boolean") {
    return null;
  }
  return payload as AccessRequestsBody;
}
