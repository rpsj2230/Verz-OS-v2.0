/**
 * What the Audit screen asks the API for, and what it may do with the answer. No React.
 *
 * The split is `skillsQuery.ts`' and `governQuery.ts`': this decides what may be asked and what a
 * row says, the page renders it, and the case that is always wrong, a filter offering something
 * it must not, is testable without mounting a table.
 *
 * **This screen is the Audit item of the Govern section in `docs/screens.html`**, which draws the
 * item in the company console's navigation and draws the overview's Activity card beside a "Full
 * audit" link: a time, who, and a sentence about what they did. The design has no screen of its
 * own for the ledger, so this is that card made whole, in its order and in its register, with the
 * filters every console screen carries.
 *
 * **Nothing here decides who may see an entry.** `brain.audit.view.AuditView` decides that on the
 * server, entry by entry, and fills a page from what survives. The request is the same for every
 * caller, and a refusal comes back as the API's own sentence.
 *
 * **A filter offers what the API offered and nothing it assembled.** The action and subject-kind
 * lists arrive on the response and are the product's own vocabularies; the people come from the
 * rows the reader was just shown. See `A_FILTER_OFFERS_WHAT_THE_ANSWER_CARRIED`.
 *
 * **No number about the rows is rendered.** Not a total, not a count of entries, not "showing".
 * `readLedgerPage` has no path from a `total` to a renderer, and the page model has no field for
 * one to arrive in.
 *
 * **The address is the state.** Filters, order, period and an open subject's history are query
 * parameters of the console address, so a colleague can be sent the view being argued about, and
 * the back button undoes a filter. The cursor is not: it is a position in one reader's view, and a
 * link carrying one would open somebody else's page part-way through theirs.
 *
 * Task ids: M27.7.13, M27.8.6
 */

import type { components } from "../api/schema";

/** One entry, as `brain.audit_routes.AuditRowView` sends it. */
export type AuditRow = components["schemas"]["AuditRowView"];
/** One change to a subject's reach, as `PermissionEventView` sends it. */
export type PermissionEvent = components["schemas"]["PermissionEventView"];

/** Written down because the tempting improvement is a dropdown of everybody in the ledger. */
export const A_FILTER_OFFERS_WHAT_THE_ANSWER_CARRIED =
  "The actions and subject kinds a filter offers are the ones the API sent, which are the " +
  "product's own words and the same in every install. The people are the actors on the rows " +
  "this reader was just shown. A list of people read from the ledger would be a list of " +
  "everybody who has done anything here, handed to a reader whose rows were withheld.";

/** Where the API keeps this screen. */
export const AUDIT_API_PATH = "/audit";
export const HISTORY_API_PATH = "/audit/history";

/** The console address. */
export const AUDIT_PATH = "/audit";

/** How many entries one page asks for. Below the route's declared maximum; see the test. */
export const AUDIT_PAGE_SIZE = 50;

/** The console address's own parameter names. The API's are in `auditApiPath`. */
export const ADDRESS_PARAMETERS = {
  search: "q",
  action: "action",
  kind: "kind",
  actor: "actor",
  period: "period",
  order: "order",
  subject: "subject",
} as const;

/** The windows a reader may choose. A closed list: a free date box is a second parser. */
export const PERIODS = ["day", "week", "month", "all"] as const;
export type Period = (typeof PERIODS)[number];

export const PERIOD_LABELS: Readonly<Record<Period, string>> = Object.freeze({
  day: "Last 24 hours",
  week: "Last 7 days",
  month: "Last 30 days",
  all: "All time",
});

const PERIOD_HOURS: Readonly<Record<Exclude<Period, "all">, number>> = Object.freeze({
  day: 24,
  week: 24 * 7,
  month: 24 * 30,
});

export const ORDERS = ["newest", "oldest"] as const;
export type Order = (typeof ORDERS)[number];

export const ORDER_LABELS: Readonly<Record<Order, string>> = Object.freeze({
  newest: "Newest first",
  oldest: "Oldest first",
});

/** What the reader narrowed the ledger by. Empty strings are unset. */
export interface AuditFilters {
  /** Words every entry shown must say, in its action, actor, subject or details. */
  readonly search: string;
  readonly action: string;
  readonly kind: string;
  readonly actor: string;
  readonly period: Period;
  readonly order: Order;
}

/** The week, newest first, which is what somebody opening an audit screen asks about first. */
export const DEFAULT_FILTERS: AuditFilters = Object.freeze({
  search: "",
  action: "",
  kind: "",
  actor: "",
  period: "week",
  order: "newest",
});

/** The filters a console address carries. An unrecognised period or order is the default. */
export function filtersFrom(search: URLSearchParams): AuditFilters {
  const period = search.get(ADDRESS_PARAMETERS.period) ?? "";
  const order = search.get(ADDRESS_PARAMETERS.order) ?? "";
  return {
    search: search.get(ADDRESS_PARAMETERS.search) ?? "",
    action: search.get(ADDRESS_PARAMETERS.action) ?? "",
    kind: search.get(ADDRESS_PARAMETERS.kind) ?? "",
    actor: search.get(ADDRESS_PARAMETERS.actor) ?? "",
    period: (PERIODS as readonly string[]).includes(period)
      ? (period as Period)
      : DEFAULT_FILTERS.period,
    order: (ORDERS as readonly string[]).includes(order) ? (order as Order) : DEFAULT_FILTERS.order,
  };
}

/** The instant a period begins, or null for all time. */
export function periodSince(period: Period, now: Date): Date | null {
  if (period === "all") {
    return null;
  }
  return new Date(now.getTime() - PERIOD_HOURS[period] * 60 * 60 * 1000);
}

/**
 * The whole request one page makes, query string included.
 *
 * Only parameters `GET /api/v1/audit` declares, which the test reads out of the API's document.
 * `since` is sent with its offset, because the route refuses a naive instant.
 */
export function auditApiPath(filters: AuditFilters, now: Date, cursor: string | null): string {
  const query = new URLSearchParams();
  query.set("limit", String(AUDIT_PAGE_SIZE));
  query.set("order", filters.order);
  if (filters.search.trim() !== "") {
    query.set("q", filters.search.trim());
  }
  if (filters.action !== "") {
    query.set("action", filters.action);
  }
  if (filters.kind !== "") {
    query.set("subject_kind", filters.kind);
  }
  if (filters.actor !== "") {
    query.set("actor", filters.actor);
  }
  const since = periodSince(filters.period, now);
  if (since !== null) {
    query.set("since", since.toISOString());
  }
  if (cursor !== null) {
    query.set("cursor", cursor);
  }
  return `${AUDIT_API_PATH}?${query.toString()}`;
}

/** The request one subject's permission history makes. */
export function historyApiPath(kind: string, id: string): string {
  const query = new URLSearchParams({ subject_kind: kind, subject_id: id });
  return `${HISTORY_API_PATH}?${query.toString()}`;
}

/**
 * An open subject, read off the address as `kind:id`, or null.
 *
 * Split at the first colon, which is the ledger's own grammar: a subject id may not contain one.
 */
export function subjectFrom(search: URLSearchParams): { kind: string; id: string } | null {
  const raw = search.get(ADDRESS_PARAMETERS.subject) ?? "";
  const at = raw.indexOf(":");
  if (at <= 0 || at === raw.length - 1) {
    return null;
  }
  return { kind: raw.slice(0, at), id: raw.slice(at + 1) };
}

/** One page of the ledger, as this console holds it. */
export interface LedgerPage {
  readonly rows: readonly AuditRow[];
  readonly nextCursor: string | null;
  readonly actions: readonly string[];
  readonly kinds: readonly string[];
  readonly actors: readonly string[];
}

const NO_PAGE: LedgerPage = Object.freeze({
  rows: [],
  nextCursor: null,
  actions: [],
  kinds: [],
  actors: [],
});

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === "string") : [];
}

/**
 * Read `brain.audit_routes.AuditLedgerPage` out of a response body.
 *
 * An unreadable body is an empty page rather than a throw, which is `readSkillsPage`' choice and
 * for its reason. There is no `total` to drop, and nothing here would read one if it arrived.
 */
export function readLedgerPage(payload: unknown): LedgerPage {
  if (typeof payload !== "object" || payload === null) {
    return NO_PAGE;
  }
  const body = payload as {
    items?: unknown;
    next_cursor?: unknown;
    actions?: unknown;
    subject_kinds?: unknown;
    actors?: unknown;
  };
  if (!Array.isArray(body.items)) {
    return NO_PAGE;
  }
  return {
    rows: body.items as AuditRow[],
    nextCursor: typeof body.next_cursor === "string" ? body.next_cursor : null,
    actions: strings(body.actions),
    kinds: strings(body.subject_kinds),
    actors: strings(body.actors),
  };
}

/** One subject's history, as this console holds it. */
export interface History {
  readonly events: readonly PermissionEvent[];
  readonly full: boolean;
}

/** Read `PermissionHistoryView` out of a response body. */
export function readHistory(payload: unknown): History {
  if (typeof payload !== "object" || payload === null) {
    return { events: [], full: false };
  }
  const body = payload as { events?: unknown; full?: unknown };
  return {
    events: Array.isArray(body.events) ? (body.events as PermissionEvent[]) : [],
    full: body.full === true,
  };
}

/**
 * The people a filter may offer: the actors the answer carried, and the one already chosen.
 *
 * The chosen actor is kept because a reader who narrowed to somebody and was shown nothing must
 * still be able to see what they chose and clear it, and it is a value they typed or clicked
 * rather than one read from the ledger.
 */
export function offeredActors(page: LedgerPage, chosen: string): readonly string[] {
  if (chosen === "" || page.actors.includes(chosen)) {
    return page.actors;
  }
  return [chosen, ...page.actors];
}

/**
 * The verb a row's action reads as, in the Activity card's register.
 *
 * Every member of `brain.audit.ledger.AuditAction` has a phrase, which the test holds against the
 * vocabulary the API's own document declares, so a thirteenth action cannot arrive rendered as
 * its code on a screen written in sentences.
 */
export const ACTION_PHRASES: Readonly<Record<string, string>> = Object.freeze({
  grant: "granted a capability to",
  revoke: "took a capability away from",
  deny: "was refused, about",
  leash_change: "changed the leash on",
  entity_merge: "merged",
  publish: "published",
  break_glass: "opened break glass on",
  compose_change: "changed what is attached to",
  approval: "decided an approval about",
  record_read: "read a record about",
  sign_in: "changed the sign-in link of",
  session_end: "ended a session of",
  certification: "reviewed",
  credential: "wrote",
  retention: "released or withdrew",
  legal_hold: "placed or lifted",
  skill: "added or decided about",
  connector: "connected or disconnected",
  setting: "switched or set",
  routing: "changed the routing rung",
  instructions: "changed the instructions of",
  webhook: "changed the webhook subscriber",
  erasure: "filed or finished",
  memory: "corrected",
  organisation: "placed in a team or made a lead, or ended",
  elevation: "asked for more, or approved or denied",
  vault_access: "answered a call about",
  principal_state: "disabled or enabled",
  breach: "opened, assessed, notified or closed",
});

/** The phrase for an action, or its code when the vocabulary has outgrown this console. */
export function phraseFor(action: string): string {
  return ACTION_PHRASES[action] ?? action;
}

/** A subject as the row names it: "principal u_wide". */
export function subjectLabel(kind: string, id: string): string {
  return `${kind} ${id}`;
}

/** The address that opens one subject's history, keeping the filters already chosen. */
export function historyAddress(search: URLSearchParams, kind: string, id: string): string {
  const next = new URLSearchParams(search);
  next.set(ADDRESS_PARAMETERS.subject, `${kind}:${id}`);
  return `${AUDIT_PATH}?${next.toString()}`;
}

/** The address with one filter changed, or removed when the value is empty. */
export function withFilter(search: URLSearchParams, name: string, value: string): string {
  const next = new URLSearchParams(search);
  if (value === "") {
    next.delete(name);
  } else {
    next.set(name, value);
  }
  const query = next.toString();
  return query === "" ? AUDIT_PATH : `${AUDIT_PATH}?${query}`;
}

/** An instant, as the rows show it. The reader's own locale and zone, to the minute. */
export function when(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ------------------------------------------------------------------- the verification job

/** One walk of the whole ledger, as `brain.audit_routes.VerificationView` sends it. */
export type Verification = components["schemas"]["VerificationView"];

/** Where the API runs the job (M24.1.2, M24.3.3). */
export const VERIFICATION_API_PATH = "/audit/verification";

/** The published head a person copies from the anchor store, as the form holds it. */
export interface PublishedHead {
  readonly seq: string;
  readonly head: string;
  readonly takenAt: string;
}

export const EMPTY_HEAD: PublishedHead = Object.freeze({ seq: "", head: "", takenAt: "" });

/** What each blank or malformed field of the published head is told. */
export const HEAD_PROBLEMS = Object.freeze({
  seq: "Copy the sequence number from the newest anchor file.",
  head: "Copy the 64-character head digest from the same anchor file.",
  takenAt: "Copy when that anchor was taken, as the anchor file writes it.",
});

/**
 * The fields of a published head that are blank or malformed, in form order. Checked here so a
 * half-copied anchor never reaches the API, which would refuse it with a less useful sentence.
 */
export function headProblems(head: PublishedHead): readonly (keyof typeof HEAD_PROBLEMS)[] {
  const problems: (keyof typeof HEAD_PROBLEMS)[] = [];
  if (!/^\d+$/.test(head.seq.trim())) {
    problems.push("seq");
  }
  if (!/^[0-9a-f]{64}$/.test(head.head.trim())) {
    problems.push("head");
  }
  if (Number.isNaN(new Date(head.takenAt.trim()).getTime()) || head.takenAt.trim() === "") {
    problems.push("takenAt");
  }
  return problems;
}

/** The request body: the published head when one is given, nothing when the chain alone is walked. */
export function verificationBody(head: PublishedHead | null): Record<string, unknown> {
  if (head === null) {
    return {};
  }
  return {
    published: {
      seq: Number(head.seq.trim()),
      head: head.head.trim(),
      taken_at: new Date(head.takenAt.trim()).toISOString(),
    },
  };
}

/** Read `VerificationView`, or null when the body is not one. */
export function readVerification(payload: unknown): Verification | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { continuous?: unknown; caveats?: unknown; completeness?: unknown };
  if (typeof body.continuous !== "boolean" || !Array.isArray(body.caveats)) {
    return null;
  }
  return payload as Verification;
}

/** What `continuous` means, in words. Never "verified": see `brain.audit.verify`. */
export function continuityInWords(found: Verification): string {
  if (found.continuous) {
    return "No entry in the ledger was edited, removed or reordered.";
  }
  const broken = found.break_found;
  return broken === null || broken === undefined
    ? "The chain does not hold."
    : `The chain stops holding at entry ${String(broken.seq)}: ${broken.reason.replace(/_/g, " ")}.`;
}

/** What `completeness` means, in words. */
export const COMPLETENESS_WORDS: Readonly<Record<string, string>> = Object.freeze({
  anchored: "The last published head is still in the ledger, unchanged.",
  unanchored: "No published head was checked, so entries removed from the end would not show.",
  anchor_missing:
    "The ledger no longer holds the entry the published head names: entries were removed or " +
    "rewritten after it was published.",
});
