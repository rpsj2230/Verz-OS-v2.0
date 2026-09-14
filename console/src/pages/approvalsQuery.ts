/**
 * What the approvals page asks the API for, and how an answer becomes the cards it draws.
 *
 * **The queue is the API's, and nothing here decides who is offered what.** `GET
 * /api/v1/approvals` answers with the cards `brain.console.approvals.card` builds for this
 * reader's reach, filtered before the queue is bounded, so an approval the reader may not
 * decide is not in the body at all. This file has nothing to filter with and filters nothing:
 * it drops a card that does not say which approval it is or what will happen, and a second
 * card for an approval already read, and carries every other card in the order it arrived.
 *
 * **Five fields a card, and the card has no sixth.** They are `Card`'s own: which suspension,
 * the artefact exactly as it was rendered, whose reach it runs under, when it was raised and
 * when it lapses. A body carrying a tool call, a count or a state beside a card reaches nothing
 * here, because the reader never takes it. See
 * `AN_APPROVAL_CARD_DRAWS_WHAT_WILL_HAPPEN_AND_COUNTS_NOTHING`.
 *
 * **The artefact is carried byte for byte.** Not trimmed, not collapsed, not re-rendered: an
 * approval of a re-rendered artefact is an approval of something nobody read, and trimming is
 * the smallest re-render there is.
 *
 * Task ids: M35.3.1.2
 */

/** Written down because an approvals screen is tempted by a count above it and a call below it. */
export const AN_APPROVAL_CARD_DRAWS_WHAT_WILL_HAPPEN_AND_COUNTS_NOTHING =
  "An approval card is what will happen, shown as it was rendered, and who it runs as. A tool " +
  "call beside it is the permission model and the client's own data on a screen chosen for " +
  "authority over an action, and a total above the queue is the number of approvals the " +
  "reader was not offered. So the page draws the cards the API sent, in its order, and no " +
  "number anywhere.";

/** Where the queue is asked for, under the API base. */
export const APPROVALS_API_PATH = "/approvals";

/** Where one approval's card is asked for, under the API base. */
export function approvalApiPath(suspensionId: string): string {
  return `${APPROVALS_API_PATH}/${encodeURIComponent(suspensionId)}`;
}

/** One approval as this console holds it. `Card`'s five fields, under this console's names. */
export interface ApprovalCardView {
  readonly suspensionId: string;
  readonly artefact: string;
  readonly runsAs: string;
  readonly raisedAt: string;
  readonly expiresAt: string;
}

/** The queue as this console holds it. Two fields, and neither is a count. */
export interface ApprovalQueueAnswer {
  readonly cards: readonly ApprovalCardView[];
  /** There are more approvals this reader may decide than the answer carried. Never how many. */
  readonly truncated: boolean;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function instant(value: unknown): string | undefined {
  const text = said(value);
  return text !== undefined && !Number.isNaN(Date.parse(text)) ? text : undefined;
}

function fieldsOf(payload: unknown): Readonly<Record<string, unknown>> | undefined {
  // A cast at the boundary, where proving a structural match buys nothing: every value is read
  // back through `said`, `instant` or an exact comparison.
  return typeof payload === "object" && payload !== null && !Array.isArray(payload)
    ? (payload as Readonly<Record<string, unknown>>)
    : undefined;
}

/**
 * One card out of a body, or `null` when the body does not say which approval it is, what will
 * happen, whose reach it runs under, and when it was raised and lapses.
 */
export function readApprovalCard(payload: unknown): ApprovalCardView | null {
  const fields = fieldsOf(payload);
  const suspensionId = said(fields?.["suspension_id"]);
  const artefact = said(fields?.["artefact"]);
  const runsAs = said(fields?.["runs_as"]);
  const raisedAt = instant(fields?.["raised_at"]);
  const expiresAt = instant(fields?.["expires_at"]);
  if (
    suspensionId === undefined ||
    artefact === undefined ||
    runsAs === undefined ||
    raisedAt === undefined ||
    expiresAt === undefined
  ) {
    return null;
  }
  return { suspensionId, artefact, runsAs, raisedAt, expiresAt };
}

/**
 * The queue out of a body, or `null` when the body is not a queue.
 *
 * `null` rather than an empty queue for a body with no `items` array, for the reason
 * `readRoster` gives: an empty queue is a claim that nothing is waiting on this reader, and a
 * body that is not a queue makes no such claim.
 */
export function readApprovalQueue(payload: unknown): ApprovalQueueAnswer | null {
  const fields = fieldsOf(payload);
  const items = fields?.["items"];
  if (fields === undefined || !Array.isArray(items)) {
    return null;
  }
  const seen = new Set<string>();
  const cards: ApprovalCardView[] = [];
  for (const item of items as readonly unknown[]) {
    const read = readApprovalCard(item);
    if (read === null || seen.has(read.suspensionId)) {
      continue;
    }
    seen.add(read.suspensionId);
    cards.push(read);
  }
  return { cards, truncated: fields["truncated"] === true };
}
