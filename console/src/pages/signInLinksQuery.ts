/**
 * What the Sign-in links page asks the API for, what its two writes send, and the sentences it
 * says about them. No React.
 *
 * **A sign-in link is which identity provider account signs in as which person.** The account is
 * never shown and never sent back: the server stores a one-way fingerprint of it, and the account
 * a person types into the link form is sent once and the field emptied whatever the answer. See
 * `AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT`.
 *
 * **Nothing here decides who may see or change a link.** The listing opens for somebody holding
 * the authority to make a link over the whole company, the store refuses to unlink the last
 * administrator under its lock, and `brain.sign_in_routes` refuses a link for the reasons it
 * names. The one check made first is the route's own grammar for the account (not empty, nothing
 * around it), so the form can say which field is wrong before a request.
 *
 * Task ids: M27.7.11, M27.8.6, M27.16.1
 */

import type { components } from "../api/schema";
import type { FieldProblem } from "../api/errors";
import type { FilterChoice, SortChoice } from "../components/listing";

/** One person who can sign in, as `brain.session_routes.SignInLinkView` sends it. */
export type LinkRow = components["schemas"]["SignInLinkView"];

/** Written down because echoing what was typed is what every form does by default. */
export const AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT =
  "The identity provider account is the one value on this screen the server refuses to store, so " +
  "the form sends it once and empties the field whatever came back. A result that repeated it, " +
  "or a field that kept it after a success, would put the account on a screen the listing was " +
  "built never to show it on.";

/** Where the API keeps this page and its two writes. */
export const LINKS_API_PATH = "/govern/sign-ins";
export const UNLINK_API_PATH = "/govern/sign-ins/unlink";
export const LINK_API_PATH = "/sign-ins";

/** The console address. */
export const SIGN_IN_LINKS_PATH = "/sign-in-links";

/** The longest account or person ID the link route takes. `brain.sign_in_routes.MAX_IDENTIFIER_CHARS`. */
export const MAX_IDENTIFIER_CHARS = 255;

/** The filters the links route declares that this page offers, over values on rows drawn. */
export const LINK_FILTERS: readonly FilterChoice<LinkRow>[] = [
  { column: "department", label: "Department", everything: "All departments", read: (row) => row.department },
];

/** The orders this page offers, as the route spells them. Empty is the route's own, by name. */
export const LINK_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "department", label: "Department" },
  { value: "-linked_at", label: "Most recently linked first" },
];

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

/** One row out of the answer, or null: carried only with a person, a name and a date. */
function readLink(item: unknown): LinkRow | null {
  if (typeof item !== "object" || item === null || Array.isArray(item)) {
    return null;
  }
  // A cast at the boundary: every field is read back through a type check below.
  const entry = item as Readonly<Record<string, unknown>>;
  const person = text(entry["principal_id"]);
  const name = text(entry["display_name"]);
  const linked = text(entry["linked_at"]);
  if (person === "" || name === "" || linked === "") {
    return null;
  }
  const department = entry["department"];
  return {
    principal_id: person,
    display_name: name,
    department: typeof department === "string" && department !== "" ? department : null,
    linked_at: linked,
    last_administrator: entry["last_administrator"] === true,
    yours: entry["yours"] === true,
  };
}

/** Read `brain.session_routes.SignInLinksPage` out of a response body. Each person once, in order. */
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
  const seen = new Set<string>();
  const links: LinkRow[] = [];
  for (const item of body.items as readonly unknown[]) {
    const row = readLink(item);
    if (row !== null && !seen.has(row.principal_id)) {
      seen.add(row.principal_id);
      links.push(row);
    }
  }
  return {
    links,
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

/** What each field of the link form takes, said under it before anything is sent. */
export const ACCOUNT_HINT =
  "The user ID your identity provider shows for this account, usually 36 letters, digits and " +
  "hyphens. Paste it exactly, with no spaces before or after.";
export const PERSON_HINT =
  "The person's ID as People and access shows it, not their name or email address. Up to 255 characters.";

/** Why a link was not sent. Each is drawn beside the field it is about. */
export const ACCOUNT_IS_EMPTY = "Enter the identity provider account ID.";
export const ACCOUNT_HAS_SPACE_AROUND_IT =
  "The account ID has space before or after it. Copy it again exactly as the identity provider " +
  "shows it.";
export const PERSON_IS_EMPTY = "Enter the person's ID, as People and access shows it.";

/** The problems with a link before it is sent, by the field each is about. */
export function linkProblems(subject: string, principalId: string): readonly FieldProblem[] {
  const problems: FieldProblem[] = [];
  if (subject === "") {
    problems.push({ field: "subject", code: "blank", message: ACCOUNT_IS_EMPTY });
  } else if (subject !== subject.trim()) {
    problems.push({ field: "subject", code: "not_exact", message: ACCOUNT_HAS_SPACE_AROUND_IT });
  }
  if (principalId.trim() === "") {
    problems.push({ field: "principal_id", code: "blank", message: PERSON_IS_EMPTY });
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
