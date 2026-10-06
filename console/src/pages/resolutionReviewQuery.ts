/**
 * What the Possible duplicates screen asks for and says. No React.
 *
 * `brain.resolution_routes` answers the pairs of records waiting for a person to say whether they
 * are one company or person, and takes that person's decision with a reason in a sentence. This
 * module holds the addresses, the readers of those shapes, and every sentence the page shows.
 *
 * **The page's own words for why a pair is here are chosen by `origin`, and the API's reason goes
 * to Advanced.** The reason the API sends is the matcher's sentence ("the cascade matched these two
 * on their names rather than on a registration number ..."), which is precise and is written for
 * whoever built the matcher. The owner asked on 2026-09-22, about the Models screen, for plain words
 * and nothing a person has to learn first, so the card leads with one of three sentences keyed on
 * the three origins the table allows (`brain.tables.resolution_review.ReviewOrigin`) and keeps the
 * exact reason beside the identifiers. Rejected: rewriting each reason the matcher can give into
 * plain words here, which is a second list of reasons that drifts from the first the day a reason
 * is added; an origin this console does not know falls back to the API's sentence as given.
 *
 * **The only figures are the cards' own.** `by_strongest` counts the pairs shown, by how strong
 * their best evidence is, and `brain.resolution.review` builds it after the reader's filter, so
 * nothing here can say how many pairs exist that this reader may not see. `strengthSummary` names
 * only bands with a pair in them and never a total of anything else. See
 * `NO_FIGURE_HERE_COUNTS_WHAT_THE_READER_WAS_NOT_SHOWN`.
 *
 * **A 409 is somebody else's decision, and its sentence is the API's.** `readNotChanged` reads the
 * `NotChangedView` body; the console adds nothing to it.
 *
 * Task ids: M14.6.4, M14.8.5
 */

import type { components } from "../api/schema";

export { readNotChanged } from "./agentAutomationsQuery";

export type ReviewQueueBody = components["schemas"]["ReviewQueueView"];
export type ReviewCard = components["schemas"]["ReviewCardView"];
export type ReviewRecord = components["schemas"]["RecordView"];
export type Decision = "merge" | "reject";

/** Written down because a helpful "and N more you cannot see" is the easy version of this page. */
export const NO_FIGURE_HERE_COUNTS_WHAT_THE_READER_WAS_NOT_SHOWN =
  "Every figure on this page is counted from the pairs drawn on it, by the API, after it has kept " +
  "back every pair whose two records this reader does not both see. A total of the queue, a " +
  "'showing 3 of 47' or a gap in a numbering would each tell the reader how many pairs they may " +
  "not see, so none is drawn and no field could carry one.";

/** Where the API keeps the queue. */
export const REVIEW_API_PATH = "/resolution/review";

/** The console address. */
export const DUPLICATES_PATH = "/duplicates";

/** The route one decision is posted to. */
export function decisionApiPath(itemId: string): string {
  return `${REVIEW_API_PATH}/${encodeURIComponent(itemId)}/decision`;
}

/** The longest reason the API accepts, from `brain.resolution_routes.ReviewDecisionAsked`. */
export const LONGEST_REASON = 400;

export const DUPLICATES_LABEL = "Possible duplicates";
export const DUPLICATES_LEDE =
  "Records from different systems that may be the same company or person. Say whether each pair is the same, and why.";

export const READING_PAIRS = "Reading the pairs waiting for you.";
export const NOTHING_WAITING_TITLE = "Nothing waiting";
/** An empty queue, which is a sentence rather than an empty page. */
export const NOTHING_WAITING =
  "No pair of records is waiting for you to decide. Pairs appear here when the Brain finds two records it cannot be sure about.";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no pair is shown. The console and the API are probably from different releases.";

export const SAME = "These are the same";
export const DIFFERENT = "These are different";
export const KEEP_WAITING = "Not now";

export const SAME_QUESTION = "Are these the same?";
export const DIFFERENT_QUESTION = "Are these different?";
export const SAME_CONSEQUENCE =
  "The two records are joined into one, so a question about either is answered from both. It is recorded in your name with your reason.";
export const DIFFERENT_CONSEQUENCE =
  "The two records stay apart and this pair is not asked about again. It is recorded in your name with your reason.";

export const REASON_LABEL = "Why, in a sentence";
export const REASON_HINT = `What you checked, such as "same registration number and address". Up to ${String(LONGEST_REASON)} characters.`;
export const REASON_MISSING = "Say why in a sentence before deciding.";
export const REASON_TOO_LONG = `Keep the reason to ${String(LONGEST_REASON)} characters or fewer.`;

export const NOT_DECIDED = "The decision was not recorded";
export const JOINED = "Joined. The two records are now one.";
export const KEPT_APART = "Kept apart. This pair will not be asked about again.";
export const ALREADY_ONE = "Recorded. The two records were already one, so nothing else changed.";

export const EVIDENCE_LABEL = "What matches";
export const NO_EVIDENCE = "Nothing about these two records matches.";
export const WAITING_SINCE = "Waiting since";
export const FROM_LABEL = "From";
export const UNMEASURED =
  "How strong each piece of evidence is was set by hand and has not yet been checked against real decisions, so treat it as a guide.";

/** Why a pair is here, by the origin the table allows, in plain words. */
export const WHY_BY_ORIGIN: Readonly<Record<string, string>> = Object.freeze({
  cascade: "The Brain could not tell on its own whether these are the same.",
  held: "The Brain thinks these are the same, and waits for a person to agree before joining them.",
  money: "The Brain thinks these are the same, and one of them holds financial records, so a person always decides.",
});

/** The card's plain sentence for why the pair is here, or the API's own when the origin is new. */
export function whyWords(card: ReviewCard): string {
  return WHY_BY_ORIGIN[card.origin] ?? sentence(card.why);
}

/** A sentence from the API, with a capital and a full stop, as a reader expects one. */
export function sentence(text: string): string {
  const trimmed = text.trim();
  if (trimmed === "") {
    return trimmed;
  }
  const capital = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}

function words(name: string): string {
  return name.replace(/[_-]+/g, " ").trim();
}

/** A connector's name as a heading word: "xero" is "Xero", "lark_base" is "Lark base". */
export function systemWords(source: string): string {
  const spaced = words(source);
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Where a record came from, in words: "a company in Hubspot". The kind drops a leading copy of the
 * connector's name, which is how connectors name their kinds ("hubspot_company").
 */
export function whereFrom(record: ReviewRecord): string {
  const prefix = `${record.source}_`;
  const kind = words(record.entity.startsWith(prefix) ? record.entity.slice(prefix.length) : record.entity);
  const article = /^[aeiou]/i.test(kind) ? "an" : "a";
  return `${kind === "" ? "a record" : `${article} ${kind}`} in ${systemWords(record.source)}`;
}

/** The confirmation's question, consequence and button, by decision. */
export function questionFor(decision: Decision): string {
  return decision === "merge" ? SAME_QUESTION : DIFFERENT_QUESTION;
}

export function consequenceFor(decision: Decision): string {
  return decision === "merge" ? SAME_CONSEQUENCE : DIFFERENT_CONSEQUENCE;
}

export function confirmLabelFor(decision: Decision): string {
  return decision === "merge" ? SAME : DIFFERENT;
}

/** What is wrong with a reason before it is sent, or null. The API judges it again. */
export function reasonProblem(reason: string): string | null {
  const trimmed = reason.trim();
  if (trimmed === "") {
    return REASON_MISSING;
  }
  return trimmed.length > LONGEST_REASON ? REASON_TOO_LONG : null;
}

/** The body one decision posts. */
export function decisionBody(decision: Decision, reason: string): { decision: Decision; reason: string } {
  return { decision, reason: reason.trim() };
}

/** What the page says after the API recorded a decision. */
export function decidedSentence(decision: Decision, merged: boolean): string {
  if (decision === "reject") {
    return KEPT_APART;
  }
  return merged ? JOINED : ALREADY_ONE;
}

/** The evidence bands, strongest first, as the API names them and as a person reads them. */
export const BANDS: readonly (readonly [string, string])[] = Object.freeze([
  ["decisive", "very nearly certain"],
  ["strong", "strong"],
  ["supporting", "some support"],
  ["weak", "weak"],
  ["against", "nothing in favour"],
]);

/**
 * The cards shown, by how strong their best evidence is, as one sentence. Only bands with a pair in
 * them are named, and nothing is counted but the cards drawn. Null when there is nothing to say.
 */
export function strengthSummary(byStrongest: Readonly<Record<string, number>>): string | null {
  const parts: string[] = [];
  for (const [band, said] of BANDS) {
    const count = byStrongest[band] ?? 0;
    if (count > 0) {
      parts.push(`${said} for ${String(count)}`);
    }
  }
  return parts.length === 0 ? null : `Best evidence on the pairs below: ${parts.join(", ")}.`;
}

/** How many pairs are drawn, which is a count of what the reader is looking at. */
export function waitingSentence(cards: number): string {
  return cards === 1 ? "1 pair is waiting for you." : `${String(cards)} pairs are waiting for you.`;
}

function isRecord(value: unknown): value is ReviewRecord {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return typeof record["source"] === "string" && typeof record["entity"] === "string" && typeof record["label"] === "string";
}

function isCard(value: unknown): value is ReviewCard {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const card = value as Record<string, unknown>;
  return (
    typeof card["item_id"] === "string" &&
    isRecord(card["left"]) &&
    isRecord(card["right"]) &&
    Array.isArray(card["lines"]) &&
    card["lines"].every((line) => typeof line === "string") &&
    typeof card["why"] === "string" &&
    typeof card["origin"] === "string"
  );
}

/** Read `brain.resolution_routes.ReviewQueueView`, or null for a shape this console does not read. */
export function readQueue(payload: unknown): ReviewQueueBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { cards?: unknown; by_strongest?: unknown };
  if (!Array.isArray(body.cards) || !body.cards.every(isCard)) {
    return null;
  }
  if (typeof body.by_strongest !== "object" || body.by_strongest === null) {
    return null;
  }
  return payload as ReviewQueueBody;
}

/** Read `ReviewDecidedView` for this item, or null. */
export function readDecided(payload: unknown, itemId: string): { readonly state: string; readonly merged: boolean } | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { item_id?: unknown; state?: unknown; merged?: unknown };
  return body.item_id === itemId && typeof body.state === "string" && typeof body.merged === "boolean"
    ? { state: body.state, merged: body.merged }
    : null;
}
