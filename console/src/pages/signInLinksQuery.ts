/**
 * What the Sign-in links screen asks the API for, and what its two writes may send. No React.
 *
 * **A sign-in link is which identity provider account signs in as which person**, and this screen
 * sits beside People and Sessions in Govern, which is where `docs/screens.html` SCREEN 10 puts who
 * a person is and how they get in. It lists the people who can sign in, links an account to a
 * person, and unlinks one.
 *
 * **The account itself is never shown and never sent back.** The server stores a one-way
 * fingerprint of it and not the account, so the listing cannot name one and says so in the API's
 * words. The account a person types into the link form is sent once and the field is emptied
 * whatever the answer, so nothing on the page repeats it. See
 * `AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT`.
 *
 * **Nothing here decides who may see or change a link.** The listing opens for somebody holding
 * the authority to make a link over the whole company, the unlink is refused for the last
 * administrator by the store under its lock, and a link is refused for the reasons
 * `brain.sign_in_routes` names. This module reads the answers and says them.
 *
 * **Checks before a write are the route's own grammar, so a person is told before a request.**
 * An empty account, or one with space around it, is refused by `brain.identity.sign_in_binding`
 * as not exactly what a token carries; this module refuses the same thing first so the form can
 * say which field is wrong rather than returning the route's code.
 *
 * Task ids: M27.7.11
 */

import type { components } from "../api/schema";

/** One person who can sign in, as `brain.session_routes.SignInLinkView` sends it. */
export type LinkRow = components["schemas"]["SignInLinkView"];

/** Written down because echoing what was typed is what every form does by default. */
export const AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT =
  "The identity provider account is the one value on this screen the server refuses to store, so " +
  "the form sends it once and empties the field whatever came back. A result that repeated it, " +
  "or a field that kept it after a success, would put the account on a screen the listing was " +
  "built never to show it on.";

/** Where the API keeps this screen and its two writes. */
export const LINKS_API_PATH = "/govern/sign-ins";
export const UNLINK_API_PATH = "/govern/sign-ins/unlink";
export const LINK_API_PATH = "/sign-ins";

/** The console address. */
export const SIGN_IN_LINKS_PATH = "/sign-in-links";

/** How many links one listing asks for. Below the route's maximum; see the test. */
export const LINKS_PAGE_SIZE = 200;

export function linksApiPath(): string {
  return `${LINKS_API_PATH}?limit=${String(LINKS_PAGE_SIZE)}`;
}

/** One page of links, as this console holds it. */
export interface LinksPage {
  readonly links: readonly LinkRow[];
  readonly truncated: boolean;
  /** Where the account is kept, in the API's words. */
  readonly account: string;
  /** What unlinking does, in the API's words. */
  readonly unlinking: string;
  /** Why the last administrator's link stays, in the API's words. */
  readonly lastAdministrator: string;
}

const NO_LINKS: LinksPage = Object.freeze({
  links: [],
  truncated: false,
  account: "",
  unlinking: "",
  lastAdministrator: "",
});

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Read `brain.session_routes.SignInLinksPage` out of a response body. */
export function readLinksPage(payload: unknown): LinksPage {
  if (typeof payload !== "object" || payload === null) {
    return NO_LINKS;
  }
  const body = payload as {
    items?: unknown;
    truncated?: unknown;
    account?: unknown;
    unlinking?: unknown;
    last_administrator?: unknown;
  };
  if (!Array.isArray(body.items)) {
    return NO_LINKS;
  }
  return {
    links: body.items as LinkRow[],
    truncated: body.truncated === true,
    account: text(body.account),
    unlinking: text(body.unlinking),
    lastAdministrator: text(body.last_administrator),
  };
}

/** The body of one unlink, as `UnlinkAsked` declares it. */
export interface UnlinkAsked {
  readonly principal_id: string;
}

/** The sentence an unlink answer carries, on a success or on the 409 that refuses the last one. */
export function unlinkSentence(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  return text((payload as { sentence?: unknown }).sentence);
}

/** The body of one link, as `brain.sign_in_routes.SignInAsked` declares it. */
export interface LinkAsked {
  readonly subject: string;
  readonly principal_id: string;
}

/** Why a link was not sent. Each is a sentence the form shows beside the field it is about. */
export const ACCOUNT_IS_EMPTY = "Enter the identity provider account ID.";
export const ACCOUNT_HAS_SPACE_AROUND_IT =
  "The account ID has space before or after it. Copy it again exactly as the identity provider " +
  "shows it.";
export const PERSON_IS_EMPTY = "Enter the person's ID, as People and grants shows it.";

/** The problems with a link before it is sent, in the order the form shows its fields. */
export function linkProblems(subject: string, principalId: string): readonly string[] {
  const problems: string[] = [];
  if (subject === "") {
    problems.push(ACCOUNT_IS_EMPTY);
  } else if (subject !== subject.trim()) {
    problems.push(ACCOUNT_HAS_SPACE_AROUND_IT);
  }
  if (principalId.trim() === "") {
    problems.push(PERSON_IS_EMPTY);
  }
  return problems;
}

/**
 * What each outcome of `POST /api/v1/sign-ins` says to the administrator who asked.
 *
 * Every code `brain.sign_in_routes.SignInOutcome` declares has a sentence, which the test holds
 * against the vocabulary in the API's own document. None names another person, because none of
 * the codes does.
 */
export const LINK_OUTCOMES: Readonly<Record<string, string>> = Object.freeze({
  bound: "Linked. That account now signs in as this person.",
  already_bound: "That account already signs in as this person. Nothing was changed.",
  subject_not_exact:
    "The account ID is not exactly as the identity provider issues it. Copy it again.",
  own_sign_in: "Nobody links an account to themselves. Ask another administrator to do it.",
  subject_bound_elsewhere:
    "That account already signs in as somebody else. Unlink it there first.",
  principal_already_signs_in:
    "This person already has a sign-in link. Unlink it first, then link the new account.",
});

/** The sentence for a link answer, or null when it is not one this console knows. */
export function linkOutcome(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const outcome = (payload as { outcome?: unknown }).outcome;
  return typeof outcome === "string" ? (LINK_OUTCOMES[outcome] ?? null) : null;
}

/** An instant, as the rows show it. The date is enough for when a link was made. */
export function linkedOn(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** The rows whose name or ID contains what was typed, ignoring case. Over the page only. */
export function matching(rows: readonly LinkRow[], typed: string): readonly LinkRow[] {
  const wanted = typed.trim().toLowerCase();
  if (wanted === "") {
    return rows;
  }
  return rows.filter(
    (row) =>
      row.display_name.toLowerCase().includes(wanted) ||
      row.principal_id.toLowerCase().includes(wanted),
  );
}
