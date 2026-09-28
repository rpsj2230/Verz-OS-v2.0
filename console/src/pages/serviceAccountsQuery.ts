/**
 * What the Service accounts screen asks `brain.service_account_routes` for and sends it, and how the
 * answers are read. No React.
 *
 * The routes existed and no screen called them, so no install could register an integration, give
 * it a key or take one away without a script (M27.11.5). `docs/screens.html` does not draw this
 * screen, so it takes the design's general shape and every fact on it is a field the API sent.
 *
 * **Nothing here decides whose account is whose.** The routes take the owner from the caller and
 * never from a field, and every body built below has no field that could name anybody else, so the
 * page cannot lend somebody else's reach even by mistake. See
 * `AN_ACCOUNT_IS_ALWAYS_THE_CALLERS_OWN`.
 *
 * **A key is read from exactly one answer and never asked for again.** The issue answers the key
 * whole once; the listing carries its handle and never its secret, and nothing here stores the key
 * anywhere but the page's own state, which is emptied when the person says they have kept it. See
 * `A_KEY_IS_SHOWN_ONCE_AND_NEVER_READ_BACK`.
 *
 * **Only blankness is judged here, before anything is sent.** A ceiling naming an approve or admin
 * capability, a wildcard, a repeated capability and an id of the wrong shape are the API's to refuse
 * and its sentences to say, beside the field it names; a second copy of those rules here is the copy
 * that drifts. `CEILING_RULE` describes the rule beside the field and decides nothing.
 *
 * Task ids: M27.11.5, M27.15.26
 */

import type { FieldProblem } from "../api/problems";
import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

export type AccountsBody = components["schemas"]["AccountsPage"];
export type AccountRow = components["schemas"]["AccountView"];
export type KeyRow = components["schemas"]["KeyView"];
export type IssuedKeyBody = components["schemas"]["KeyIssued"];
export type RegistrationBody = components["schemas"]["AccountAsked"];
export type KeyBody = components["schemas"]["KeyAsked"];
export type RevocationBody = components["schemas"]["KeyRevocation"];
export type RetirementBody = components["schemas"]["AccountRetirement"];

/** The rule a reviewer must not break: no body sent from this screen names an owner. */
export const AN_ACCOUNT_IS_ALWAYS_THE_CALLERS_OWN =
  "Every account on this screen is the signed-in person's own. The routes take the owner from the " +
  "caller, and no body sent from here has a field that could name anybody else.";

/** The rule a reviewer must not break: the key lives in one answer and in the page until kept. */
export const A_KEY_IS_SHOWN_ONCE_AND_NEVER_READ_BACK =
  "A key is read from the answer that issued it and from nowhere else. It is held in the page only " +
  "until the person says they have kept it, is never stored in the browser, and no request asks " +
  "for it again, because no route could answer one.";

/** Where the API keeps the screen, and the three writes beneath it. */
export const SERVICE_ACCOUNTS_API_PATH = "/govern/service-accounts";
export const ISSUE_KEY_API_PATH = "/govern/service-accounts/keys";
export const REVOKE_KEY_API_PATH = "/govern/service-accounts/keys/revoke";
export const RETIRE_ACCOUNT_API_PATH = "/govern/service-accounts/retire";

/** The console address and the menu's label. */
export const SERVICE_ACCOUNTS_PATH = "/service-accounts";
export const SERVICE_ACCOUNTS_LABEL = "Service accounts";

/** The filter the listing route declares that this screen offers, over capabilities on rows drawn. */
export const ACCOUNT_FILTERS: readonly FilterChoice<AccountRow>[] = [
  { column: "ceiling", label: "Capability", everything: "Every capability", read: (row) => row.ceiling },
];

/** The orders this screen offers, as the route spells them. Empty is the route's own, newest first. */
export const ACCOUNT_SORTS: readonly SortChoice[] = [
  { value: "", label: "Newest first" },
  { value: "client_id", label: "By account ID" },
  { value: "label", label: "By name" },
  { value: "lapses_at", label: "Soonest to stop working first" },
];

/** What the account ID field says about the shape the API holds. It decides nothing. */
export const ID_SHAPE =
  "Begins svc_, then lower-case letters, digits and underscores, such as svc_weekly_report.";

/** What the ceiling field says about the rule the API holds. It decides nothing. */
export const CEILING_RULE =
  "One capability per line, each named in full, such as read:invoice. Read, write and invoke only: " +
  "a service account can never carry an approve or admin capability, and a wildcard is refused.";

/** How a key is rotated with these controls, which is the only way one is. */
export const ROTATION =
  "To rotate a key without a gap, issue a new one, move the integration to it, and then revoke the " +
  "old one.";

/** What each field left blank is told, before anything is sent. */
export const BLANK_SENTENCES = Object.freeze({
  client_id: "Give the account an id, such as the name of the integration that will use it.",
  ceiling: "List at least one capability the account may use.",
  not_after: "Choose the day the account stops working. Every account has an end.",
  key_not_after: "Choose the day the key stops working. It is also capped at the account's own end.",
});

/** Read `AccountsPage` out of a response body, or null when it is not one. */
export function readAccounts(payload: unknown): AccountsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { items?: unknown; truncated?: unknown };
  if (!Array.isArray(body.items) || typeof body.truncated !== "boolean") {
    return null;
  }
  return payload as AccountsBody;
}

/** Read `KeyIssued` out of a response body, or null when it carries no key. */
export function readIssuedKey(payload: unknown): IssuedKeyBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { key?: unknown; handle?: unknown; client_id?: unknown };
  if (typeof body.key !== "string" || body.key === "" || typeof body.handle !== "string") {
    return null;
  }
  return payload as IssuedKeyBody;
}

/** The sentence a revocation or a retirement answered with, or nothing. */
export function toldBy(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

/** The capabilities typed into the ceiling field, one per line or comma, trimmed, blanks dropped. */
export function ceilingFrom(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((one) => one.trim())
    .filter((one) => one !== "");
}

/**
 * The end of the chosen day in the reader's own time zone, as the aware instant the routes require,
 * or null for no day. A date input gives a day and the routes refuse a time with no zone.
 */
export function endOfDay(day: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
    return null;
  }
  const moment = new Date(`${day}T23:59:59`);
  return Number.isNaN(moment.getTime()) ? null : moment.toISOString();
}

/** The blank fields of a registration, as the problems the API would have answered with. */
export function blankRegistrationProblems(clientId: string, ceiling: string, lapsesOn: string): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (clientId.trim() === "") {
    found.push({ field: "client_id", code: "blank", message: BLANK_SENTENCES.client_id });
  }
  if (ceilingFrom(ceiling).length === 0) {
    found.push({ field: "ceiling", code: "blank", message: BLANK_SENTENCES.ceiling });
  }
  if (endOfDay(lapsesOn) === null) {
    found.push({ field: "not_after", code: "blank", message: BLANK_SENTENCES.not_after });
  }
  return found;
}

/** A key's end left blank, as the problem the API would have answered with. */
export function blankKeyProblems(lapsesOn: string): FieldProblem[] {
  return endOfDay(lapsesOn) === null
    ? [{ field: "not_after", code: "blank", message: BLANK_SENTENCES.key_not_after }]
    : [];
}

/**
 * The body a registration sends: the fields the route declares and no owner. The identity provider
 * subject is sent only when one was typed, because the route refuses an empty one.
 */
export function registrationBody(
  clientId: string,
  label: string,
  ceiling: string,
  lapsesOn: string,
  subject: string,
): RegistrationBody {
  const body: RegistrationBody = {
    client_id: clientId.trim(),
    label: label.trim(),
    ceiling: ceilingFrom(ceiling),
    not_after: endOfDay(lapsesOn) ?? "",
  };
  return subject.trim() === "" ? body : { ...body, subject: subject.trim() };
}

/** The body a key issue sends. */
export function keyBody(clientId: string, label: string, lapsesOn: string): KeyBody {
  return { client_id: clientId, label: label.trim(), not_after: endOfDay(lapsesOn) ?? "" };
}

/** The body a revocation sends. */
export function revocationBody(handle: string): RevocationBody {
  return { handle };
}

/** The body a retirement sends. */
export function retirementBody(clientId: string): RetirementBody {
  return { client_id: clientId };
}

/** What a person sees in the date columns. */
export function when(stamp: string | null | undefined): string {
  if (!stamp) {
    return "";
  }
  const moment = new Date(stamp);
  return Number.isNaN(moment.getTime()) ? stamp : moment.toISOString().replace("T", " ").slice(0, 16);
}

/** How an account is named in a sentence: its label when it has one, its id otherwise. */
export function accountName(row: Pick<AccountRow, "label" | "client_id">): string {
  return row.label.trim() === "" ? row.client_id : row.label;
}

/** Every live key on the page, each beside the account it belongs to, in the API's order. */
export function keysOf(accounts: readonly AccountRow[]): { account: AccountRow; key: KeyRow }[] {
  return accounts.flatMap((account) => account.keys.map((key) => ({ account, key })));
}
