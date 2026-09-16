/**
 * What the Learning screen asks the API for, and what its three tiers are. No React.
 *
 * **This screen is SCREEN 8 of `docs/screens.html`, and the design's one table is three here.**
 * The design lists every learning in one "What changed" table with a Tier column.
 * `brain.console.govern_estate.learning_review` returns the tiers as three tuples and refuses one
 * list, because a single list sorted by anything puts a proposal waiting for a person next to a
 * change that has already happened, with a control beside each that means something different.
 * So the page draws one table per tier under the design's heading, in the design's tier order,
 * with the design's columns where a tier has them. See `THREE_TIERS_ARE_THREE_TABLES`.
 *
 * **The figures are counts of the rows this reader was shown, and say so.** Since 2026-09-17
 * `mem.learning` stores what a learning proposed, so an empty tier is an install where nothing in
 * this reader's view has been learnt rather than a store that does not exist. Every figure is over
 * the rows the API sent, which were narrowed to what this reader may recall before they were sent,
 * so a figure is never a count of what they were not shown.
 *
 * **Undo is a confirmed write, offered only where the API says this reader may press it.** Each
 * tier-one row carries `undo_offered`, which is the server's `may_undo` asked of that row, and the
 * confirmation shows the sentence the API serves for what the undo will write. The page decides
 * nothing: a row offered no undo shows none, and a refused undo is the API's own sentence. See
 * `UNDO_IS_ASKED_OF_THE_SERVER_ROW_BY_ROW`. There is still no promote or decide control, because
 * nothing records agreement or a decision.
 *
 * **Tier three is null for a reader who may not be told where gated changes went**, which is not
 * the same as none having gone anywhere, and the page says which it is.
 *
 * Served by `brain.console.govern_estate`, through `brain.estate_routes`.
 *
 * Task ids: M27.7.21
 */

import type { components } from "../api/schema";

export type TierOne = components["schemas"]["TierOneView"];
export type TierTwo = components["schemas"]["TierTwoView"];
export type TierThree = components["schemas"]["TierThreeView"];
export type TierRule = components["schemas"]["TierRuleView"];

/** Written down because SCREEN 8 draws one table and a reader comparing the two will ask. */
export const THREE_TIERS_ARE_THREE_TABLES =
  "SCREEN 8 lists every learning in one table with a Tier column. The review this page renders " +
  "keeps the tiers as three separate lists, because a change that has already happened and a " +
  "proposal waiting for a person sorted into one list sit side by side with controls that mean " +
  "different things. So What changed is three tables, one per tier, in the design's order.";

/** Written down because an undo control drawn from this page's own idea would be a second rule. */
export const UNDO_IS_ASKED_OF_THE_SERVER_ROW_BY_ROW =
  "Whether a person may undo a learning depends on where its memory was formed and on the " +
  "authority they hold there, and the server answers it per row as undo_offered. The page draws " +
  "the control where the API offers it and nowhere else, so a person is never shown a button the " +
  "server would refuse, and never refused a button they could not see.";

/** Where the API keeps this screen. */
export const LEARNING_API_PATH = "/govern/learning";

/** Where one undo is posted. */
export const UNDO_API_PATH = "/govern/learning/undo";

/** The body one undo sends: the memory's id and nothing else, as `UndoAsked` declares. */
export function undoBody(memoryId: string): { readonly memory_id: string } {
  return { memory_id: memoryId };
}

/** The console address, at the screen's own key in `brain.console.screens`. */
export const LEARNING_PATH = "/learning";

/** The window the design's first figure covers. */
export const RECENT_DAYS = 7;

/** One review, as this console holds it. */
export interface LearningPage {
  readonly basis: string;
  /** The instant the API assembled the review at, so "recent" is its clock and not this one. */
  readonly asOf: string;
  readonly tierOne: readonly TierOne[];
  readonly tierTwo: readonly TierTwo[];
  /** Null when this reader may not be shown where gated changes were routed. */
  readonly tierThree: readonly TierThree[] | null;
  readonly tiers: readonly TierRule[];
  /** How many learnings the review reads at most. A constant, the same for every reader. */
  readonly considered: number;
  /** What the confirmation says an undo will write, keyed by `control_writes`. */
  readonly undoSays: Readonly<Record<string, string>>;
  readonly staleness: string | null;
}

const NOTHING: LearningPage = Object.freeze({
  basis: "own",
  asOf: "",
  tierOne: [],
  tierTwo: [],
  tierThree: null,
  tiers: [],
  considered: 0,
  // Empty on an unreadable body, so no undo can be confirmed in words the API did not send.
  undoSays: {},
  staleness: null,
});

/** Read `brain.estate_routes.LearningReviewView` out of a response body. */
export function readLearningPage(payload: unknown): LearningPage {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as {
    basis?: unknown;
    as_of?: unknown;
    tier_one?: unknown;
    tier_two?: unknown;
    tier_three?: unknown;
    tiers?: unknown;
    considered?: unknown;
    undo_says?: unknown;
    staleness?: unknown;
  };
  if (!Array.isArray(body.tier_one) || !Array.isArray(body.tier_two)) {
    return NOTHING;
  }
  const staleness = body.staleness as { message?: unknown } | null | undefined;
  return {
    basis: typeof body.basis === "string" ? body.basis : "own",
    asOf: typeof body.as_of === "string" ? body.as_of : "",
    tierOne: body.tier_one as TierOne[],
    tierTwo: body.tier_two as TierTwo[],
    tierThree: Array.isArray(body.tier_three) ? (body.tier_three as TierThree[]) : null,
    tiers: Array.isArray(body.tiers) ? (body.tiers as TierRule[]) : [],
    considered: typeof body.considered === "number" ? body.considered : 0,
    undoSays: readUndoSays(body.undo_says),
    staleness: typeof staleness?.message === "string" ? staleness.message : null,
  };
}

function readUndoSays(payload: unknown): Readonly<Record<string, string>> {
  if (typeof payload !== "object" || payload === null) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(payload as Record<string, unknown>).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

/** What one undo answered: whether it wrote anything, and the API's sentence. */
export interface Undone {
  readonly tookEffect: boolean;
  readonly told: string;
}

/** Read `brain.estate_routes.LearningUndoneView` out of a response body. */
export function readUndone(payload: unknown): Undone {
  if (typeof payload !== "object" || payload === null) {
    return { tookEffect: false, told: "" };
  }
  const body = payload as { took_effect?: unknown; told?: unknown };
  return {
    tookEffect: body.took_effect === true,
    told: typeof body.told === "string" ? body.told : "",
  };
}

/** The sentence a considered bound is stated in, identical for every reader. */
export function consideredSentence(considered: number): string {
  return `This review reads at most the ${String(considered)} most recently recorded learnings of the agents you may see.`;
}

/**
 * How many tier-one and tier-two learnings on this page were learnt in the last `days` days
 * before the API's own instant. Tier three carries no instant and is not counted.
 */
export function learnedRecently(page: LearningPage, days: number = RECENT_DAYS): number {
  const until = Date.parse(page.asOf);
  if (Number.isNaN(until)) {
    return 0;
  }
  const since = until - days * 24 * 60 * 60 * 1000;
  return [...page.tierOne, ...page.tierTwo].filter((row) => {
    const at = Date.parse(row.learned_at);
    return at > since && at <= until;
  }).length;
}

/** What each tier is, in SCREEN 8's own words for its four-tier card. */
export const TIER_WORDS: Readonly<Record<number, { readonly what: string; readonly how: string }>> =
  {
    0: { what: "Silent, within one conversation", how: "ends with the conversation" },
    1: { what: "Applies by itself", how: "automatic, and undoable" },
    2: { what: "Proves itself in shadow first", how: "shadow, then promote" },
    3: { what: "Changes who may see what", how: "a person decides" },
  };
