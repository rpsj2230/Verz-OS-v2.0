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
 * **Nothing on this install records a learning, and the page says that rather than drawing
 * zeroes.** `brain.estate_routes` sends `learnings_are_not_recorded`, and while it is true every
 * figure on the page is a sentence: "0 learned this week" would read as a system that learnt
 * nothing, which nobody established. See `A_ZERO_NOBODY_COUNTED_IS_A_CLAIM`.
 *
 * **There is no undo, promote or decide control, and there is no path here one could be posted
 * to.** Undoing a tier-one learning writes a correction and nothing stores one; the API sends
 * `undo_is_not_writable` and the page says so where the design draws the button.
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

/** Written down because every figure on SCREEN 8 would otherwise be a zero. */
export const A_ZERO_NOBODY_COUNTED_IS_A_CLAIM =
  "While nothing on this install records a learning, a figure of zero learned, zero applied " +
  "and zero waiting reads as a system that has learnt nothing and has nothing waiting, which " +
  "nobody measured. The figures are sentences until the API says learnings are recorded.";

/** Where the API keeps this screen. */
export const LEARNING_API_PATH = "/govern/learning";

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
  readonly learningsAreNotRecorded: boolean;
  readonly undoIsNotWritable: boolean;
}

const NOTHING: LearningPage = Object.freeze({
  basis: "own",
  asOf: "",
  tierOne: [],
  tierTwo: [],
  tierThree: null,
  tiers: [],
  // True on an unreadable body, for `readSkillsPage`' reason.
  learningsAreNotRecorded: true,
  undoIsNotWritable: true,
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
    learnings_are_not_recorded?: unknown;
    undo_is_not_writable?: unknown;
  };
  if (!Array.isArray(body.tier_one) || !Array.isArray(body.tier_two)) {
    return NOTHING;
  }
  return {
    basis: typeof body.basis === "string" ? body.basis : "own",
    asOf: typeof body.as_of === "string" ? body.as_of : "",
    tierOne: body.tier_one as TierOne[],
    tierTwo: body.tier_two as TierTwo[],
    tierThree: Array.isArray(body.tier_three) ? (body.tier_three as TierThree[]) : null,
    tiers: Array.isArray(body.tiers) ? (body.tiers as TierRule[]) : [],
    learningsAreNotRecorded: body.learnings_are_not_recorded !== false,
    undoIsNotWritable: body.undo_is_not_writable !== false,
  };
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
